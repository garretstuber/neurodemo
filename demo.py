# -*- coding: utf-8 -*-
"""
NeuroDemo - Physiological neuron sandbox for educational purposes
Luke Campagnola 2015
"""
from __future__ import division, unicode_literals
import numpy as np

# make sure we get the right pyqtgraph..
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg
import pyqtgraph.multiprocess as mp
import pyqtgraph.parametertree as pt
from neurodemo.units import *
from neurodemo.neuronview import NeuronView
from neurodemo.channelparam import ChannelParameter
from neurodemo.clampparam import ClampParameter

pg.setConfigOption('antialias', True)
app = pg.mkQApp()


class DemoWindow(QtGui.QWidget):
    def __init__(self):
        # set up simulation in remote process
        self.dt = 25*us
        self.proc = mp.QtProcess(debug=False)
        ndemo = self.proc._import('neurodemo')
        self.sim = ndemo.Sim(temp=6.3, dt=self.dt)
        self.sim._setProxyOptions(deferGetattr=True)
        self.neuron = ndemo.Section(name='soma')
        self.sim.add(self.neuron)
        
        self.hhna = self.neuron.add(ndemo.HHNa())
        self.leak = self.neuron.add(ndemo.Leak())
        self.hhk = self.neuron.add(ndemo.HHK())
        self.dexh = self.neuron.add(ndemo.IH())
        self.dexh.enabled = False
        
        self.clamp = self.neuron.add(ndemo.PatchClamp(mode='ic'))
        #cmd = np.zeros(int(1/self.dt))
        #cmd[int(0.4/self.dt):int(0.8/self.dt)] = 200e-12
        #self.clamp.set_command(cmd, dt=self.dt)
        
        mechanisms = [self.clamp, self.hhna, self.leak, self.hhk, self.dexh]

        # loop to run the simulation indefinitely
        self.runner = ndemo.SimRunner(self.sim)
        #self.runner.add_request('soma.Vm') 
        self.runner.add_request('t') 
        self.runner.new_result.connect(mp.proxy(self.new_result, autoProxy=False, callSync='off'))

        
        # set up GUI
        QtGui.QWidget.__init__(self)
        self.fullscreen_widget = None
        self.resize(1024, 768)
        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        
        self.splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)
        self.layout.addWidget(self.splitter, 0, 0)
        
        self.ptree = pt.ParameterTree(showHeader=False)
        self.splitter.addWidget(self.ptree)
        
        self.plot_splitter = QtGui.QSplitter(QtCore.Qt.Vertical)
        self.splitter.addWidget(self.plot_splitter)
        
        self.neuronview = NeuronView(self.neuron, mechanisms)
        self.plot_splitter.addWidget(self.neuronview)
        
        #self.vm_plot = ScrollingPlot(dt=self.dt, npts=int(1.0/self.dt),
                                         #parent=self, labels={'left': ('Membrane Potential', 'V'), 
                                                              #'bottom': ('Time', 's')})
        #self.vm_plot.setYRange(-90*mV, 50*mV)
        #self.vm_plot.setXRange(-1000*ms, 0*ms)
        #self.vm_plot.addLine(y=self.neuron.ek)
        #self.vm_plot.addLine(y=self.neuron.ena)
        #self.plot_splitter.addWidget(self.vm_plot)
        self.channel_plots = {}
        
        
        self.channel_params = [
            ChannelParameter(self.leak),
            ChannelParameter(self.hhna),
            ChannelParameter(self.hhk),
            ChannelParameter(self.dexh),
        ]
        for ch in self.channel_params:
            ch.plots_changed.connect(self.plots_changed)

        self.clamp_param = ClampParameter(self.clamp, self)
        self.clamp_param.plots_changed.connect(self.plots_changed)


        self.vm_plot = self.add_plot('soma.V', 'Membrane Potential', 'V')
        
        self.splitter.setSizes([350, 650])

        self.show()

        
        self.params = pt.Parameter.create(name='params', type='group', children=[
            dict(name='Preset', type='list', values=['', 'Passive Membrane', 'Action Potential']),
            dict(name='Run', type='bool', value=True),
            dict(name='Speed', type='float', value=0.3, limits=[0, 10], step=1, dec=True),
            dict(name='Temp', type='float', value=self.sim.temp, suffix='C', step=1.0),
            dict(name='Capacitance', type='float', value=self.neuron.cap, suffix='F', siPrefix=True, dec=True),
            dict(name='Cell Schematic', type='bool', value=True, children=[
                dict(name='Show Circuit', type='bool', value=False),
            ]),
            self.clamp_param,
            dict(name='Ion Channels', type='group', children=self.channel_params),
        ])
        self.ptree.setParameters(self.params)
        self.params.sigTreeStateChanged.connect(self.params_changed)
        
        self.start()

        self.clamp_param['Plot Current'] = True
        self.plot_splitter.setSizes([300, 500, 200])
        
        self.pause_shortcut = QtGui.QShortcut(QtGui.QKeySequence('Space'), self)
        self.pause_shortcut.activated.connect(self.pause)
        self.slow_shortcut = QtGui.QShortcut(QtGui.QKeySequence('-'), self)
        self.slow_shortcut.activated.connect(self.slower)
        self.fast_shortcut = QtGui.QShortcut(QtGui.QKeySequence('='), self)
        self.fast_shortcut.activated.connect(self.faster)
        self.fullscreen_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F11'), self)
        self.fullscreen_shortcut.activated.connect(self.fullscreen)
        self.fullscreen_shortcut.setContext(QtCore.Qt.ApplicationShortcut)

    def params_changed(self, root, changes):
        for param, change, val in changes:
            if change != 'value':
                continue
            if param is self.params.child('Run'):
                if val:
                    self.start()
                else:
                    self.stop()
            elif param is self.params.child('Speed'):
                self.runner.set_speed(val)
            elif param is self.params.child('Temp'):
                self.sim.temp = val
            elif param is self.params.child('Capacitance'):
                self.neuron.cap = val
            elif param is self.params.child('Preset'):
                self.load_preset(val)
            elif param is self.params.child('Cell Schematic'):
                self.neuronview.setVisible(val)
            elif param is self.params.child('Cell Schematic', 'Show Circuit'):
                self.neuronview.show_circuit(val)
        
    def plots_changed(self, param, channel, name, plot):
        key = channel.name + '.' + name
        if plot:
            self.add_plot(key, param.name(), name)
        else:
            self.remove_plot(key)

    def add_plot(self, key, pname, name):
        # decide on y range, label, and units for new plot
        yranges = {
            'V': (-100*mV, 50*mV),
            'I': (-1*nA, 1*nA),
            'G': (0, 100*nS),
            'OP': (0, 1),
            'm': (0, 1),
            'h': (0, 1),
            'n': (0, 1),
        }
        color = {'I': 'c', 'G': 'y', 'OP': 'g', 'V': 'w'}.get(name, 0.7)
        units = {'I': 'A', 'G': 'S', 'V': 'V'}
        label = pname + ' ' + name
        if name in units:
            label = (label, units[name])
            
        # create new plot
        plt = ScrollingPlot(dt=self.dt, npts=int(1.0 / self.dt),
                            labels={'left': label}, pen=color)
        if hasattr(self, 'vm_plot'):
            plt.setXLink(self.vm_plot)
        else:
            plt.setXRange(-1, 0)
        plt.setYRange(*yranges.get(name, (0, 1)))
        
        # register this plot for later..
        self.channel_plots[key] = plt
        self.runner.add_request(key)
        
        # add new plot to splitter and resize all accordingly
        sizes = self.plot_splitter.sizes()
        self.plot_splitter.addWidget(plt)
        size = self.plot_splitter.height() / (len(sizes) + 1.)
        r = len(sizes) / (len(sizes)+1)
        sizes = [s * r for s in sizes] + [size]
        self.plot_splitter.setSizes(sizes)
        
        # Ask sequence plotter to update as well
        self.clamp_param.add_plot(key, label)
        return plt
            
    def remove_plot(self, key):
        plt = self.channel_plots.pop(key)
        self.runner.remove_request(key)
        self.clamp_param.remove_plot(key)
        plt.setParent(None)
        plt.close()
        
    def start(self):
        self.runner.start(blocksize=100)
        
    def stop(self):
        self.runner.stop()
        
    def pause(self):
        self.params['Run'] = not self.params['Run']

    def slower(self):
        self.params['Speed'] *= 0.5
        
    def faster(self):
        self.params['Speed'] = min(self.params['Speed'] * 2.0, 10)

    def fullscreen(self):
        if self.fullscreen_widget is None:
            w = QtGui.QApplication.focusWidget()
            ind = self.plot_splitter.indexOf(w)
            if ind < 0:
                return
            self.fs_widget_index = ind
            w.setParent(None)
            w.showFullScreen()
            self.fullscreen_widget = w
        else:
            self.fullscreen_widget.showNormal()
            self.plot_splitter.insertWidget(self.fs_widget_index, self.fullscreen_widget)
            self.fullscreen_widget = None
        
    def new_result(self, final_state, result):
        for k, plt in self.channel_plots.items():
            if k not in result:
                continue
            plt.append(result[k][1:])
            
        # Let the clamp decide which triggered regions of the data to extract
        # for pulse plots
        self.clamp_param.new_result(result)
        
        # update the schematic
        self.neuronview.update_state(final_state)

    def load_preset(self, preset):
        if preset == 'Passive Membrane':
            self.params['Temp'] = 6.3
            self.params['Speed'] = 0.05
            self.params['Patch Clamp', 'Plot Current'] = False
            self.params['Patch Clamp', 'Plot Voltage'] = False
            chans = self.params.child('Ion Channels')
            chans['soma.Ileak'] = True
            chans['soma.Ileak', 'Erev'] = 0
            chans['soma.INa'] = False
            chans['soma.IK'] = False
            chans['soma.IH'] = False
        elif preset == 'Action Potential':
            self.params['Temp'] = 6.3
            self.params['Speed'] = 0.05
            chans = self.params.child('Ion Channels')
            chans['soma.Ileak'] = True
            chans['soma.Ileak', 'Erev'] = -55*mV
            chans['soma.INa'] = True
            chans['soma.IK'] = True
            chans['soma.IH'] = False
            
        self.params['Preset'] = ''

    def closeEvent(self, ev):
        self.runner.stop()
        self.proc.close()
        QtGui.QApplication.instance().quit()


class ScrollingPlot(pg.PlotWidget):
    def __init__(self, dt, npts, pen='w', **kwds):
        pg.PlotWidget.__init__(self, **kwds)
        self.showGrid(True, True)
        self.data_curve = self.plot(pen=pen)
        self.data = np.array([], dtype=float)
        self.npts = npts
        self.dt = dt
        
    def append(self, data):
        self.data = np.append(self.data, data)
        if len(self.data) > self.npts:
            self.data = self.data[-self.npts:]
        t = np.arange(len(self.data)) * self.dt
        t -= t[-1]
        self.data_curve.setData(t, self.data)


if __name__ == '__main__':
    import sys
    win = DemoWindow()
    if sys.flags.interactive == 0:
        app.exec_()
