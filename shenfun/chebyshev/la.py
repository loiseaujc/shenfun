#pylint: disable=line-too-long, missing-docstring

from copy import copy
import numpy as np
from shenfun.optimization import la, Matvec
from shenfun.la import TDMA as la_TDMA
from shenfun.utilities import inheritdocstrings
from . import bases

@inheritdocstrings
class TDMA(la_TDMA):

    def __call__(self, b, u=None, axis=0):

        v = self.mat.testfunction[0]
        bc = v.bc

        if u is None:
            u = b
        else:
            assert u.shape == b.shape
            u[:] = b[:]

        bc.apply_before(u, False, scales=(-np.pi/2., -np.pi/4.))

        if not self.dd.shape[0] == self.mat.shape[0]:
            self.init()

        if len(u.shape) == 3:
            la.TDMA_SymSolve3D(self.dd, self.ud, self.L, u, axis)
            #la.TDMA_SymSolve3D_ptr(self.dd[self.s], self.ud[self.s], self.L,
                                   #u[self.s], axis)
        elif len(u.shape) == 2:
            la.TDMA_SymSolve2D(self.dd, self.ud, self.L, u, axis)

        elif len(u.shape) == 1:
            la.TDMA_SymSolve(self.dd, self.ud, self.L, u)

        else:
            raise NotImplementedError

        bc.apply_after(u, False)

        u /= self.mat.scale
        return u


class Helmholtz(object):
    r"""Helmholtz solver

    .. math::

        \alpha u'' + \beta u = b

    where :math:`u` is the solution, :math:`b` is the right hand side and
    :math:`\alpha` and :math:`\beta` are scalars, or arrays of scalars for
    a multidimensional problem.

    The user must provide mass and stiffness matrices and scale arrays
    :math:`(\alpha/\beta)` to each matrix. The matrices and scales can be
    provided as either kwargs or args

    As 4 arguments

    Parameters
    ----------
        A : SpectralMatrix
            Stiffness matrix (Dirichlet or Neumann)
        B : SpectralMatrix
            Mass matrix (Dirichlet or Neumann)
        alfa : Numpy array
        beta : Numpy array

    or as a dict with keys

    Parameters
    ----------
        ADDmat : A
            Stiffness matrix (Dirichlet basis)
        BDDmat : B
            Mass matrix (Dirichlet basis)
        ANNmat : A
            Stiffness matrix (Neumann basis)
        BNNmat : B
            Mass matrix (Neumann basis)

    where :math:`\alpha` and :math:`\beta` are avalable as A.scale and B.scale.

    Attributes
    ----------
        axis : int
            The axis over which to solve for
        neumann : bool
            Whether or not bases are Neumann
        bc : BoundaryValues
            For Dirichlet problem with inhomogeneous boundary values

    Variables are extracted from the matrices

    The solver can be used along any axis of a multidimensional problem. For
    example, if the Chebyshev basis (Dirichlet or Neumann) is the last in a
    3-dimensional TensorProductSpace, where the first two dimensions use Fourier,
    then the 1D Helmholtz equation arises when one is solving the 3D Poisson
    equation

    .. math::

        \nabla^2 u = b

    With the spectral Galerkin method we multiply this equation with a test
    function (:math:`v`) and integrate (weighted inner product :math:`(\cdot, \cdot)_w`)
    over the domain

    .. math::

        (v, \nabla^2 u)_w = (v, b)_w


    See :ref:`demo:poisson3d`
    for details, since it is actually quite involved. But basically, one
    obtains a linear algebra system to be solved along the :math:`z`-axis for
    all combinations of the two Fourier indices :math:`k` and :math:`l`

    .. math::

        (A_{mj} - (k^2 + l^2) B_{mj}) \hat{u}[k, l, j] = (v, b)_w[k, l, m]

    Note that :math:`k` only varies along :math:`x`-direction, whereas :math:`l`
    varies along :math:`y`. To allow for Numpy broadcasting these two variables
    are stored as arrays of shape

    .. math::

        k : (N, 1, 1)

        l : (1, M, 1)

    Here it is assumed that the solution array :math:`\hat{u}` has shape
    (N, M, P). Now, multiplying k array with :math:`\hat{u}` is achieved as an
    elementwise multiplication

    .. math::

        k \cdot \hat{u}

    Numpy will then take care of broadcasting :math:`k` to an array of shape
    (N, M, P) before performing the elementwise multiplication. Likewise, the
    constant scale :math:`1` in front of the :math:`A_{mj}` matrix is
    stored with shape (1, 1, 1), and multiplying with :math:`\hat{u}` is
    performed as if it was a scalar (as it here happens to be).

    This is where the scale arrays in the signature to the Helmholt solver comes
    from. :math:`\alpha` is here :math:`1`, whereas :math:`\beta` is
    :math:`(k^2+l^2)`. Note that :math:`k+l` is an array of shape (N, M, 1).

    """
    def __init__(self, *args, **kwargs):

        if 'ADDmat' in kwargs or 'ANNmat' in kwargs:
            if 'ADDmat' in kwargs:
                assert 'BDDmat' in kwargs
                A = self.A = kwargs['ADDmat']
                B = self.B = kwargs['BDDmat']

            if 'ANNmat' in kwargs:
                assert 'BNNmat' in kwargs
                A = self.A = kwargs['ANNmat']
                B = self.B = kwargs['BNNmat']
            alfa = self.alfa = A.scale
            beta = self.beta = B.scale

        elif len(args) == 4:
            A = self.A = args[0]
            B = self.B = args[1]
            alfa = self.alfa = args[2]
            beta = self.beta = args[3]
        else:
            raise RuntimeError('Wrong input to Helmholtz solver')

        shape = list(beta.shape)
        B[2] = np.broadcast_to(B[2], A[2].shape)
        B[-2] = np.broadcast_to(B[-2], A[2].shape)
        neumann = self.neumann = isinstance(A.testfunction[0], bases.ShenNeumannBasis)
        if not self.neumann:
            self.bc = A.testfunction[0].bc

        if len(shape) == 1:
            N = A.shape[0]+2
            self.u0 = np.zeros(N-2, float)     # Diagonal entries of U
            self.u1 = np.zeros(N-4, float)     # Diagonal+1 entries of U
            self.u2 = np.zeros(N-6, float)     # Diagonal+2 entries of U
            self.L = np.zeros(N-4, float)      # The single nonzero row of L
            self.axis = 0
            la.LU_Helmholtz_1D(A, B, alfa, beta, neumann, self.u0,
                               self.u1, self.u2, self.L)

        else:
            self.axis = A.axis
            assert alfa.shape[A.axis] == 1 and beta.shape[A.axis] == 1

            N = A.shape[0]+2
            alfa = np.broadcast_to(alfa, shape).copy()
            shape[A.axis] = N-2
            self.u0 = np.zeros(shape, float)     # Diagonal entries of U
            shape[A.axis] = N-4
            self.u1 = np.zeros(shape, float)     # Diagonal+2 entries of U
            self.L = np.zeros(shape, float)      # The single nonzero row of L
            shape[A.axis] = N-6
            self.u2 = np.zeros(shape, float)     # Diagonal+4 entries of U
            self.beta = beta.copy()

            if len(shape) == 2:
                la.LU_Helmholtz_2D(A, B, A.axis, alfa, beta, neumann,
                                   self.u0, self.u1, self.u2, self.L)

            elif len(shape) == 3:
                la.LU_Helmholtz_3D(A, B, A.axis, alfa, beta, neumann,
                                   self.u0, self.u1, self.u2, self.L)

    def __call__(self, u, b):
        """Solve matrix problem

        Parameters
        ----------
            b : array
                Array of right hand side on entry and solution on exit unless
                u is provided.
            u : array
                Output array

        If b and u are multidimensional, then the axis over which to solve for is
        determined on creation of the class.

        """

        # comment since self.beta[s0]
        #if not self.neumann:
            #if isinstance(self.bcs, BoundaryValues):
                ##self.bcs.apply_before(b, True)
                #pass

            #else:
                #s0 = [slice(0, 1)]*u.ndim
                #b[s0] -= np.pi/2*(self.bc[0] + self.bc[1])*self.beta[s0]
                #s = copy(s0)
                #s[self.axis] = slice(1, 2)
                #b[s] -= np.pi/4*(self.bc[0] - self.bc[1])*self.beta[s0]

        if np.ndim(u) == 3:

            #la.Solve_Helmholtz_3D(self.axis, b, u, self.neumann, self.u0, self.u1,
                                  #self.u2, self.L)

            la.Solve_Helmholtz_3D_ptr(self.axis, b, u, self.neumann, self.u0,
                                      self.u1, self.u2, self.L)

            #la.Solve_Helmholtz_3D_hc(self.axis, b, u, self.neumann, self.u0,
                                      #self.u1, self.u2, self.L)


        elif np.ndim(u) == 2:

            la.Solve_Helmholtz_2D(self.axis, b, u, self.neumann, self.u0, self.u1,
                                  self.u2, self.L)

            #la.Solve_Helmholtz_2D_ptr(self.axis, b, u, self.neumann, self.u0,
            #                          self.u1, self.u2, self.L)

        else:
            la.Solve_Helmholtz_1D(b, u, self.neumann, self.u0, self.u1, self.u2, self.L)

        if not self.neumann:
            self.bc.apply_after(u, True)

        return u

    def matvec(self, v, c, axis=0):
        """Matrix vector product c = dot(self, v)

        Parameters
        ----------
            v : array
            c : array

        Returns
        -------
            c : array
        """
        assert self.neumann is False
        c[:] = 0
        if len(v.shape) == 3:
            Matvec.Helmholtz_matvec3D(v, c, 1.0, self.beta, self.A[0], self.A[2], self.B[0], axis)
        elif len(v.shape) == 2:
            Matvec.Helmholtz_matvec2D(v, c, 1.0, self.beta, self.A[0], self.A[2], self.B[0], axis)
        else:
            Matvec.Helmholtz_matvec(v, c, self.alfa, self.beta, self.A[0], self.A[2], self.B[0])
        return c


class Biharmonic(object):
    r"""Multidimensional Biharmonic solver for

    .. math::

        a_0 u'''' + \alpha u'' + \beta u = b

    where :math:`u` is the solution, :math:`b` is the right hand side and
    :math:`a_0, \alpha` and :math:`\beta` are scalars, or arrays of scalars for
    a multidimensional problem.

    The user must provide mass, stiffness and biharmonic matrices and scale
    arrays :math:`(a_0/\alpha/\beta)`. The matrices and scales can be provided
    as either kwargs or args

    As 6 arguments

    Parameters
    ----------
        S : SpectralMatrix
            Biharmonic matrix
        A : SpectralMatrix
            Stiffness matrix
        B : SpectralMatrix
            Mass matrix
        a0 : array
        alfa : array
        beta : array

    or as dict with key/values

    Parameters
    ----------
        SBBmat : S
            Biharmonic matrix
        ABBmat : A
            Stiffness matrix
        BBBmat : B
            Mass matrix

    where a0, alfa and beta must be avalable as S.scale, A.scale, B.scale.

    Attributes
    ----------
        axis : int
            The axis over which to solve for

    Variables are extracted from the matrices

    The solver can be used along any axis of a multidimensional problem. For
    example, if the Chebyshev basis (Biharmonic) is the last in a
    3-dimensional TensorProductSpace, where the first two dimensions use Fourier,
    then the 1D equation listed above arises when one is solving the 3D biharmonic
    equation

    .. math::

        \nabla^4 u = b

    With the spectral Galerkin method we multiply this equation with a test
    function (:math:`v`) and integrate (weighted inner product :math:`(\cdot, \cdot)_w`)
    over the domain

    .. math::

        (v, \nabla^4 u)_w = (v, b)_w

    See `the Poisson problem <https://rawgit.com/spectralDNS/shenfun/master/docs/src/mekit17/pub/._shenfun_bootstrap004.html#sec:tensorproductspaces>`_
    for details, since it is actually quite involved. But basically, one obtains
    a linear algebra system to be solved along the :math:`z`-axis for all combinations
    of the two Fourier indices :math:`k` and :math:`l`

    .. math::

        (S_{mj} - 2(k^2 + l^2) A_{mj}) + (k^2 + l^2)^2 B_{mj}) \hat{u}[k, l, j] = (v, b)_w[k, l, m]

    Note that :math:`k` only varies along :math:`x`-direction, whereas :math:`l` varies along
    :math:`y`. To allow for Numpy broadcasting these two variables are stored as arrays of
    shape

    .. math::

        k : (N, 1, 1)

        l : (1, M, 1)

    Here it is assumed that the solution array :math:`\hat{u}` has shape
    (N, M, P). Now, multiplying :math:`k` array with :math:`\hat{u}` is achieved as

    .. math::

        k \cdot \hat{u}

    Numpy will then take care of broadcasting :math:`k` to an array of shape (N, M, P)
    before performing the elementwise multiplication. Likewise, the constant
    scale :math:`1` in front of the :math:`A_{mj}` matrix is stored with
    shape (1, 1, 1), and multiplying with :math:`\hat{u}` is performed as if it
    was a scalar (as it here happens to be).

    This is where the scale arrays in the signature to the Helmholt solver comes
    from. :math:`a_0` is here :math:`1`, whereas :math:`\alpha` and
    :math:`\beta` are :math:`-2(k^2+l^2)` and :math:`(k^2+l^2)^2`, respectively.
    Note that :math:`k+l` is an array of shape (N, M, 1).
    """
    def __init__(self, *args, **kwargs):

        if 'SBBmat' in kwargs:
            assert 'ABBmat' in kwargs and 'BBBmat' in kwargs
            S, A, B = kwargs['SBBmat'], kwargs['ABBmat'], kwargs['BBBmat']
            a0, alfa, beta = S.scale, A.scale, B.scale

        elif len(args) == 6:
            S, A, B = args[0], args[1], args[2]
            a0, alfa, beta = args[3], args[4], args[5]
        else:
            raise RuntimeError('Wrong input to Biharmonic solver')
        self.S, self.A, self.B = S, A, B
        self.alfa, self.beta = alfa, beta
        self.a0 = a0
        sii, siu, siuu = S[0], S[2], S[4]
        ail, aii, aiu = A[-2], A[0], A[2]
        bill, bil, bii, biu, biuu = B[-4], B[-2], B[0], B[2], B[4]
        M = sii[::2].shape[0]

        if np.ndim(beta) > 1:
            shape = list(beta.shape)
            self.axis = S.axis
            shape[S.axis] = M
            ss = copy(shape)
            ss.insert(0, 2)
            a0 = self.a0

            self.u0 = np.zeros(ss)
            self.u1 = np.zeros(ss)
            self.u2 = np.zeros(ss)
            self.l0 = np.zeros(ss)
            self.l1 = np.zeros(ss)
            self.ak = np.zeros(ss)
            self.bk = np.zeros(ss)
            if np.ndim(beta) == 3:
                la.LU_Biharmonic_3D_n(S.axis, a0[0,0,0], alfa, beta, sii, siu, siuu,
                                      ail, aii, aiu, bill, bil, bii, biu, biuu,
                                      self.u0, self.u1, self.u2, self.l0,
                                      self.l1)
                la.Biharmonic_factor_pr_3D(S.axis, self.ak, self.bk, self.l0,
                                           self.l1)

            elif np.ndim(beta) == 2:
                la.LU_Biharmonic_2D_n(S.axis, a0[0,0], alfa, beta, sii, siu, siuu,
                                      ail, aii, aiu, bill, bil, bii, biu, biuu,
                                      self.u0, self.u1, self.u2, self.l0,
                                      self.l1)
                la.Biharmonic_factor_pr_2D(S.axis, self.ak, self.bk, self.l0,
                                           self.l1)

        else:
            self.u0 = np.zeros((2, M))
            self.u1 = np.zeros((2, M))
            self.u2 = np.zeros((2, M))
            self.l0 = np.zeros((2, M))
            self.l1 = np.zeros((2, M))
            self.ak = np.zeros((2, M))
            self.bk = np.zeros((2, M))
            la.LU_Biharmonic_1D(a0, alfa, beta, sii, siu, siuu, ail, aii, aiu,
                                bill, bil, bii, biu, biuu, self.u0, self.u1,
                                self.u2, self.l0, self.l1)
            la.Biharmonic_factor_pr(self.ak, self.bk, self.l0, self.l1)

    def __call__(self, u, b):
        """Solve matrix problem

        Parameters
        ----------
            b : array
                Array of right hand side on entry and solution on exit unless
                u is provided.
            u : array
                Output array

        If b and u are multidimensional, then the axis over which to solve for is
        determined on creation of the class.

        """

        if np.ndim(u) == 3:
            la.Solve_Biharmonic_3D_n(self.axis, b, u, self.u0, self.u1,
                                     self.u2, self.l0, self.l1, self.ak,
                                     self.bk, self.a0[0,0,0])

        elif np.ndim(u) == 2:
            la.Solve_Biharmonic_2D_n(self.axis, b, u, self.u0, self.u1,
                                     self.u2, self.l0, self.l1, self.ak,
                                     self.bk, self.a0[0,0])

        else:
            la.Solve_Biharmonic_1D(b, u, self.u0, self.u1, self.u2, self.l0,
                                   self.l1, self.ak, self.bk, self.a0[0])

        return u

    def matvec(self, v, c, axis=0):
        N = v.shape[0]
        c[:] = 0
        if len(v.shape) == 3:
            Matvec.Biharmonic_matvec3D(v, c, self.a0[0,0,0], self.alfa, self.beta, self.S[0], self.S[2],
                                self.S[4], self.A[-2], self.A[0], self.A[2],
                                self.B[-4], self.B[-2], self.B[0], self.B[2], self.B[4], axis)
        elif len(v.shape) == 2:
            Matvec.Biharmonic_matvec2D(v, c, self.a0[0,0], self.alfa, self.beta, self.S[0], self.S[2],
                                self.S[4], self.A[-2], self.A[0], self.A[2],
                                self.B[-4], self.B[-2], self.B[0], self.B[2], self.B[4], axis)
        else:
            Matvec.Biharmonic_matvec(v, c, self.a0, self.alfa, self.beta, self.S[0], self.S[2],
                                self.S[4], self.A[-2], self.A[0], self.A[2],
                                self.B[-4], self.B[-2], self.B[0], self.B[2], self.B[4])
        return c


class PDMA(object):
    r"""Pentadiagonal matrix solver

    Pentadiagonal matrix with diagonals in offsets -4, -2, 0, 2, 4

    Arising with Poisson equation and biharmonic basis u

    .. math::

        \alpha u'' + \beta u = f

    As 4 arguments

    Parameters
    ----------
        A : SpectralMatrix
            Stiffness matrix
        B : SpectralMatrix
            Mass matrix
        alfa : array
        beta : array

    or as dict with key/vals

    Parameters
    ----------
        solver : str
            Choose between implementations ('cython', 'python')
        ABBmat : A
            Stiffness matrix
        BBBmat : B
            Mass matrix

    where alfa and beta must be avalable as A.scale, B.scale.

    Attributes
    ----------
        axis : int
            The axis over which to solve for

    Variables are extracted from the matrices

    """

    def __init__(self, *args, **kwargs):
        if 'ABBmat' in kwargs:
            assert 'BBBmat' in kwargs
            A = self.A = kwargs['ABBmat']
            B = self.B = kwargs['BBBmat']
            alfa = self.alfa = A.scale
            beta = self.beta = B.scale

        elif len(args) == 4:
            A = self.A = args[0]
            B = self.B = args[1]
            alfa = self.alfa = args[2]
            beta = self.beta = args[3]
        else:
            raise RuntimeError('Wrong input to PDMA solver')

        self.solver = kwargs.get('solver', 'cython')
        self.d, self.u1, self.u2 = (np.zeros_like(B[0]), np.zeros_like(B[2]),
                                    np.zeros_like(B[4]))
        self.l1, self.l2 = np.zeros_like(B[2]), np.zeros_like(B[4])
        shape = list(beta.shape)

        if len(shape) == 1:
            if self.solver == 'python':
                H = self.alfa[0]*self.A + self.beta[0]*self.B
                self.d[:] = H[0]
                self.u1[:] = H[2]
                self.u2[:] = H[4]
                self.l1[:] = H[-2]
                self.l2[:] = H[-4]
                self.PDMA_LU(self.l2, self.l1, self.d, self.u1, self.u2)

            elif self.solver == 'cython':
                la.LU_Helmholtz_Biharmonic_1D(self.A, self.B, self.alfa[0],
                                              self.beta[0], self.l2, self.l1,
                                              self.d, self.u1, self.u2)
        else:

            self.axis = A.axis
            assert alfa.shape[A.axis] == 1
            assert beta.shape[A.axis] == 1
            N = A.shape[0]+4
            alfa = np.broadcast_to(alfa, shape).copy()
            shape[A.axis] = N-4
            self.d = np.zeros(shape, float)     # Diagonal entries of U
            shape[A.axis] = N-6
            self.u1 = np.zeros(shape, float)     # Diagonal+2 entries of U
            self.l1 = np.zeros(shape, float)     # Diagonal-2 entries of U
            shape[A.axis] = N-8
            self.u2 = np.zeros(shape, float)     # Diagonal+4 entries of U
            self.l2 = np.zeros(shape, float)     # Diagonal-4 entries of U
            self.beta = beta.copy()

            if len(shape) == 2:
                raise NotImplementedError

            elif len(shape) == 3:
                la.LU_Helmholtz_Biharmonic_3D(A, B, A.axis, alfa, beta, self.l2,
                                              self.l1, self.d, self.u1, self.u2)

    @staticmethod
    def PDMA_LU(l2, l1, d, u1, u2): # pragma: no cover
        """LU decomposition of PDM (for testing only)"""
        n = d.shape[0]
        m = u1.shape[0]
        k = n - m

        for i in range(n-2*k):
            lam = l1[i]/d[i]
            d[i+k] -= lam*u1[i]
            u1[i+k] -= lam*u2[i]
            l1[i] = lam
            lam = l2[i]/d[i]
            l1[i+k] -= lam*u1[i]
            d[i+2*k] -= lam*u2[i]
            l2[i] = lam

        i = n-4
        lam = l1[i]/d[i]
        d[i+k] -= lam*u1[i]
        l1[i] = lam
        i = n-3
        lam = l1[i]/d[i]
        d[i+k] -= lam*u1[i]
        l1[i] = lam


    @staticmethod
    def PDMA_Solve(l2, l1, d, u1, u2, b): # pragma: no cover
        """Solve method for PDM (for testing only)"""
        n = d.shape[0]
        bc = np.full_like(b, b)

        bc[2] -= l1[0]*bc[0]
        bc[3] -= l1[1]*bc[1]
        for k in range(4, n):
            bc[k] -= (l1[k-2]*bc[k-2] + l2[k-4]*bc[k-4])

        bc[n-1] /= d[n-1]
        bc[n-2] /= d[n-2]
        bc[n-3] /= d[n-3]
        bc[n-3] -= u1[n-3]*bc[n-1]/d[n-3]
        bc[n-4] /= d[n-4]
        bc[n-4] -= u1[n-4]*bc[n-2]/d[n-4]
        for k in range(n-5, -1, -1):
            bc[k] /= d[k]
            bc[k] -= (u1[k]*bc[k+2]/d[k] + u2[k]*bc[k+4]/d[k])
        b[:] = bc

    def __call__(self, u, b):
        """Solve matrix problem

        Parameters
        ----------
            b : array
                Array of right hand side on entry and solution on exit unless
                u is provided.
            u : array
                Output array

        If b and u are multidimensional, then the axis over which to solve for
        is determined on creation of the class.

        """
        if np.ndim(u) == 3:
            la.Solve_Helmholtz_Biharmonic_3D_ptr(self.A.axis, b, u, self.l2,
                                                 self.l1, self.d, self.u1,
                                                 self.u2)
        else:
            if self.solver == 'python': # pragma: no cover
                u[:] = b
                self.PDMA_Solve(self.l2, self.l1, self.d, self.u1, self.u2, u)

            elif self.solver == 'cython':
                if u is b:
                    u = np.zeros_like(b)
                #la.Solve_Helmholtz_Biharmonic_1D(b, u, self.l2, self.l1,
                #                                 self.d, self.u1, self.u2)
                la.Solve_Helmholtz_Biharmonic_1D_p(b, u, self.l2, self.l1,
                                                   self.d, self.u1, self.u2)

        #u /= self.mat.scale
        return u

