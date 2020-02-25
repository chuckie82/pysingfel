import sys
sys.path.append("../..")

import os
import numpy as np
import numba
import matplotlib
import matplotlib.pyplot as plt
import h5py as h5
import time

from matplotlib.backends.qt_compat import QtWidgets, QtCore, is_pyqt5
if is_pyqt5():
    from matplotlib.backends.backend_qt5agg import (
            FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
else:
    from matplotlib.backends.backend_qt4agg import (
        FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure
from matplotlib.colors import LogNorm
from mpl_toolkits.mplot3d import Axes3D

import pysingfel as ps
import pysingfel.gpu as pg


# Set default matplotlib parameters
matplotlib.rcParams['image.origin'] = 'lower'
matplotlib.rcParams['image.interpolation'] = None
matplotlib.rcParams['image.cmap'] = 'jet'


# Create a particle object
particle = ps.Particle()
particle.read_pdb('../input/pdb/3iyf.pdb', ff='WK')
# import pysingfel.constants as cst
# particle.create_from_atoms([  # Angstrom
#     ("O", cst.vecx),
#     ("O", cst.vecy),
#     ("O", cst.vecz),
#     ("O", (cst.vecx+cst.vecy)/2),
# ])

# Load beam
beam = ps.Beam('../input/beam/amo86615.beam') 

# Load and initialize the detector
det = ps.PnccdDetector(
    geom='../input/lcls/amo86615/PNCCD::CalibV1/'
         'Camp.0:pnCCD.1/geometry/0-end.data', 
    beam=beam)

mesh_length = 151

mesh, voxel_length = det.get_reciprocal_mesh(voxel_number_1d=mesh_length)

volume = pg.calculate_diffraction_pattern_gpu(
    mesh, particle, return_type='intensity')

pixel_momentum = det.pixel_position_reciprocal


class ApplicationWindow(QtWidgets.QMainWindow):
    def __init__(self, debug=False):
        super(ApplicationWindow, self).__init__()
        self.debug = debug

        self._azim = None
        self._elev = None
        self._time = 0.
        self._uptodate = False

        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        layout = QtWidgets.QHBoxLayout(self._main)

        real3d_canvas = FigureCanvas(Figure(figsize=(5, 5)))
        layout.addWidget(real3d_canvas)
        self.addToolBar(NavigationToolbar(real3d_canvas, self))

        self._real3d_ax = real3d_canvas.figure.subplots(subplot_kw={"projection":'3d'})
        self._real3d_ax.plot(
            -particle.atom_pos[:, 2],
            particle.atom_pos[:, 1],
            particle.atom_pos[:, 0],
            ".")

        if self.debug:
            real2d_canvas = FigureCanvas(Figure(figsize=(5, 5)))
            layout.addWidget(real2d_canvas)
            self.addToolBar(NavigationToolbar(real2d_canvas, self))

            self._real2d_ax = real2d_canvas.figure.subplots()

        recip_canvas = FigureCanvas(Figure(figsize=(5, 5)))
        layout.addWidget(recip_canvas)
        self.addToolBar(NavigationToolbar(recip_canvas, self))

        self._recip_ax = recip_canvas.figure.subplots()

        self._timer = recip_canvas.new_timer(
            100, [(self._update_canvas, (), {})])
        self._timer.start()

    def _update_canvas(self):
        azim = np.radians(self._real3d_ax.azim)
        elev = np.radians(self._real3d_ax.elev)

        if azim != self._azim or elev != self._elev:
            # Record and mark for update
            self._azim = azim
            self._elev = elev
            self._time = time.time()
            self._uptodate = False
            return

        if self._uptodate:
            return

        if time.time() - self._time < 1.:
            # Wait a bit more
            return

        self._uptodate = True

        axis_azim = np.array([1., 0., 0.])
        axis_elev = np.array([0., 1., 0.])
        rot_azim = ps.geometry.angle_axis_to_rot3d(axis_azim, -azim)
        rot_elev = ps.geometry.angle_axis_to_rot3d(axis_elev, elev)
        rot = np.matmul(rot_elev, rot_azim)

        if self.debug:
            print("{:.2f} - {:.2f}".format(azim, elev))

            rpos = np.matmul(rot, particle.atom_pos.T)

            self._real2d_ax.clear()
            self._real2d_ax.plot(
                rpos[1],
                rpos[0],
                ".")
            self._real2d_ax.figure.canvas.draw()

        quat = ps.geometry.rotmat_to_quaternion(rot)
        slice_ = ps.geometry.take_slice(
        volume, voxel_length, pixel_momentum, quat, inverse=True)
        img = det.assemble_image_stack(slice_)
        self._recip_ax.clear()
        self._recip_ax.imshow(img, norm=LogNorm())
        self._recip_ax.figure.canvas.draw()


app = QtWidgets.QApplication(sys.argv)

window = ApplicationWindow(debug=False)
window.show()

app.exec_()
