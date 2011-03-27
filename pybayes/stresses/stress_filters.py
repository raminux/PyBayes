# Copyright (c) 2010 Matej Laitl <matej@laitl.cz>
# Distributed under the terms of the GNU General Public License v2 or any
# later version of the license, at your option.

"""Stresses for kalman filters"""

import os.path
import time

import numpy as np
from scipy.io import loadmat, savemat

import pybayes as pb


def stress_kalman(options, timer):
    input_file = options.datadir + "/stress_kalman_data.mat"
    output_file = "stress_kalman_res.mat"

    run_kalman_on_mat_data(input_file, output_file, timer)

def run_kalman_on_mat_data(input_file, output_file, timer):
    d = loadmat(input_file, struct_as_record=True, mat_dtype=True)

    mu0 = np.reshape(d.pop('mu0'), (-1,))  # otherwise we would get 2D array of shape (1xN)
    P0 = d.pop('P0')
    y = d.pop('y').T
    u = d.pop('u').T

    gauss = pb.GaussPdf(mu0, P0)
    kalman = pb.KalmanFilter(d['A'], d['B'], d['C'], d['D'], d['Q'], d['R'], gauss)

    N = y.shape[0]
    n = mu0.shape[0]
    Mu_py = np.zeros((N, n))

    timer.start()
    for t in xrange(1, N):  # the 1 start offset is intentional
        Mu_py[t] = kalman.bayes(y[t], u[t]).mu
    timer.stop()

    Mu_py = Mu_py.T
    savemat(output_file, {"Mu_py":Mu_py, "exec_time_pybayes":timer.spent[0]}, oned_as='row')

class PfOptions(object):
    """Class that represents options for a particle filter"""

    def __init__(self, nr_steps):
        print "Preparing data for particle filter stresses..."
        self.nr_steps = nr_steps

        # prepare random vector components:
        a_t, b_t = pb.RVComp(1, 'a_t'), pb.RVComp(1, 'b_t')  # state in t
        a_tp, b_tp = pb.RVComp(1, 'a_{t-1}'), pb.RVComp(1, 'b_{t-1}')  # state in t-1

        # prepare callback functions
        sigma_sq = np.array([0.0001])
        def f(cond):  # log(b_{t-1}) - 1/2 \sigma^2
            return np.log(cond) - sigma_sq/2.
        def g(cond):  # \sigma^2
            return sigma_sq

        # prepare p(x_t | x_{t-1}) density:
        p1 = pb.LinGaussCPdf(1., 0., 1., 0., pb.RV(a_t), pb.RV(a_tp, b_t))
        p2 = pb.GaussCPdf(1, 1, f, g, rv=pb.RV(b_t), cond_rv=pb.RV(b_tp), base_class=pb.LogNormPdf)
        self.p_xt_xtp = pb.ProdCPdf((p1, p2), pb.RV(a_t, b_t), pb.RV(a_tp, b_tp))

        # prepare p(y_t | x_t) density:
        self.p_yt_xt = pb.LinGaussCPdf(1., 0., 1., 0.)

        # initial setup: affect particles and initially set state
        self.init_range = np.array([[11.8, 0.3], [12.2, 0.7]]) # from .. to
        init_mean = (self.init_range[0] + self.init_range[1])/2.

        x_t = np.zeros((nr_steps, 2))
        x_t[0] = init_mean.copy()
        y_t = np.empty((nr_steps, 1))
        for i in range(nr_steps):
            # set b_t:
            x_t[i,1] = i/100. + init_mean[1]
            # simulate random process:
            x_t[i,0:1] = p1.sample(x_t[i])  # this is effectively [a_{t-1}, b_t]
            y_t[i] = self.p_yt_xt.sample(x_t[i])
            # DEBUG: print "simulated x_{0} = {1}".format(i, x_t[i])
            # DEBUG: print "simulated y_{0} = {1}".format(i, y_t[i])
        self.x_t = x_t
        self.y_t = y_t

pf_nr_steps = 200  # number of steps for particle filter
pf_opts = PfOptions(pf_nr_steps)

def stress_pf_1(options, timer):
    run_pf(options, timer, pf_opts, 16)

def stress_pf_2(options, timer):
    run_pf(options, timer, pf_opts, 32)

def stress_pf_3(options, timer):
    run_pf(options, timer, pf_opts, 64)

def stress_pf_4(options, timer):
    run_pf(options, timer, pf_opts, 128)

def run_pf(options, timer, pf_opts, nr_particles):
    nr_steps = pf_opts.nr_steps # number of time steps

    # construct initial particle density and particle filter:
    init_pdf = pb.UniPdf(pf_opts.init_range[0], pf_opts.init_range[1])
    pf = pb.ParticleFilter(nr_particles, init_pdf, pf_opts.p_xt_xtp, pf_opts.p_yt_xt)

    x_t = pf_opts.x_t
    y_t = pf_opts.y_t
    cumerror = np.zeros(2)  # vector of cummulative square error
    timer.start()
    for i in range(nr_steps):
        apost = pf.bayes(y_t[i])
        cumerror += (apost.mean() - x_t[i])**2
        # DEBUG: print "simulated x_{0} = {1}".format(i, x_t[i])
        # DEBUG: print "returned mean  = {0}".format(apost.mean())
    timer.stop()
    print "  {0}-particle filter cummulative error for {1} steps: {2}".format(
        nr_particles, nr_steps, np.sqrt(cumerror))

def stress_pf_old(options, timer):
    raise Exception("Stress skipped")
    nr_particles = 100  # number of particles
    nr_steps = 50 # number of time steps

    # prepare random vector components:
    a_t, b_t = pb.RVComp(1, 'a_t'), pb.RVComp(1, 'b_t')  # state in t
    a_tp, b_tp = pb.RVComp(1, 'a_{t-1}'), pb.RVComp(1, 'b_{t-1}')  # state in t-1

    # prepare callback functions
    def f(x):  # take a_t out of [a_t, b_t]
        return x[0:1]
    def g(x):  # exponential of b_t out of [a_t, b_t]
        return np.exp(x[1:2])
    #def g(x):  # take b_t out of [a_t, b_t]
        #return x[1:2]

    # prepare p(x_t | x_{t-1}) density:
    cov, A, b = np.array([[1.]]), np.array([[1.]]), np.array([0.])  # params for p1
    p1 = pb.MLinGaussCPdf(cov, A, b, pb.RV(a_t), pb.RV(a_tp))
    p2 = pb.LinGaussCPdf(1., 0., 1., 0., pb.RV(b_t), pb.RV(b_tp, a_tp))
    p_xt_xtp = pb.ProdCPdf((p1, p2), pb.RV(a_t, b_t), pb.RV(a_tp, b_tp))

    # prepare p(y_t | x_t) density:
    p_yt_xt = pb.GaussCPdf(1, 2, f, g)

    # construct initial particle density and particle filter:
    init_pdf = pb.UniPdf(np.array([2., -10.]), np.array([3., -3.]))
    pf = pb.ParticleFilter(nr_particles, init_pdf, p_xt_xtp, p_yt_xt)

    x_t = np.array([0., -10.])
    y_t = np.empty(1)
    timer.start()
    for i in range(nr_steps):
        x_t[0] = 2.5 + i/50.  # set a_t

        # simulate random process:
        x_t[1:2] = p2.sample(x_t[np.array([1, 0])])  # this is effectively b_t = sample from p [b_{t-1}, a_{t-1}]
        print "simulated x_{0} = {1}".format(i, x_t)
        y_t = p_yt_xt.sample(x_t)
        print "simulated y_{0} = {1}".format(i, y_t)

        #print pf.emp.particles
        apost = pf.bayes(y_t)
        print "returned mean = {0}".format(apost.mean())
        print
    timer.stop()
