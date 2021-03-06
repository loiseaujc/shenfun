__author__ = "Mikael Mortensen <mikaem@math.uio.no>"
__date__ = "2017-11-01"
__copyright__ = "Copyright (C) 2017 " + __author__
__license__  = "GNU Lesser GPL version 3 or any later version"
"""
Simple spectral Navier-Stokes solver

Not implemented for efficiency. For efficiency use the Navier-Stokes
solver in the https://github.com/spectralDNS/spectralDNS repository
"""

import numpy as np
from mpi4py import MPI
from shenfun import *

nu = 0.000625
end_time = 0.1
dt = 0.01
comm = MPI.COMM_WORLD
N = (2**5, 2**5, 2**5)

V0 = Basis(N[0], 'F', dtype='D')
V1 = Basis(N[1], 'F', dtype='D')
V2 = Basis(N[2], 'F', dtype='d')
T = TensorProductSpace(comm, (V0, V1, V2), **{'planner_effort': 'FFTW_MEASURE'})
TV = VectorTensorProductSpace(T)
u = TrialFunction(T)
v = TestFunction(T)

U = Array(TV)
U_hat = Function(TV)
K = np.array(T.local_wavenumbers(True, True, eliminate_highest_freq=False)) # No elim because used for second order diff
K2 = np.sum(K*K, 0, dtype=int)
K_over_K2 = K.astype(float) / np.where(K2 == 0, 1, K2).astype(float)
P_hat = Function(T)
curl_hat = Function(TV)
curl_ = Array(TV)
X = T.local_mesh(True)

def LinearRHS(**params):
    #L = inner(nu*div(grad(u)), v)  # L is shape (N[0], N[1], N[2]//2+1), but used as (3, N[0], N[1], N[2]//2+1) due to broadcasting
    L = -nu*K2  # Or just simply this
    return L

def NonlinearRHS(U, U_hat, dU, **params):
    global TV, curl_hat, curl_, P_hat, K, K_over_K2
    dU.fill(0)
    curl_hat.fill(0)
    curl_hat = project(curl(U_hat), TV, output_array=curl_hat)
    curl_ = TV.backward(curl_hat, curl_)
    U = U_hat.backward(U)
    W = np.cross(U, curl_, axis=0)                   # Nonlinear term in physical space
    #dU = project(W, TV, output_array=dU)            # dU = TV.forward(W, dU)
    dU = TV.forward(W, dU)
    P_hat = np.sum(dU*K_over_K2, 0, out=P_hat)
    dU -= P_hat*K
    return dU

if __name__ == '__main__':
    for integrator in (RK4, ETDRK4):
        # Initialization
        U[0] = np.sin(X[0])*np.cos(X[1])*np.cos(X[2])
        U[1] =-np.cos(X[0])*np.sin(X[1])*np.cos(X[2])
        U[2] = 0
        U_hat = TV.forward(U, U_hat)
        # Solve
        integ = integrator(TV, L=LinearRHS, N=NonlinearRHS)
        integ.setup(dt)
        U_hat = integ.solve(U, U_hat, dt, (0, end_time))
        # Check accuracy
        U = TV.backward(U_hat, U)
        k = comm.reduce(0.5*np.sum(U*U)/np.prod(np.array(N)))
        if comm.Get_rank() == 0:
            assert np.round(k - 0.124953117517, 7) == 0
