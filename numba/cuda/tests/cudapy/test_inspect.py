import numpy as np

from io import StringIO
from numba import cuda, float32, float64, int32, intp
from numba.cuda.testing import unittest, CUDATestCase
from numba.cuda.testing import (skip_on_cudasim, skip_with_nvdisasm,
                                skip_without_nvdisasm)


@skip_on_cudasim('Simulator does not generate code to be inspected')
class TestInspect(CUDATestCase):
    @property
    def cc(self):
        return cuda.current_context().device.compute_capability

    def test_monotyped(self):
        @cuda.jit("(float32, int32)")
        def foo(x, y):
            pass

        file = StringIO()
        foo.inspect_types(file=file)
        typeanno = file.getvalue()
        # Function name in annotation
        self.assertIn("foo", typeanno)
        # Signature in annotation
        self.assertIn("(float32, int32)", typeanno)
        file.close()
        # Function name in LLVM
        self.assertIn("foo", foo.inspect_llvm())

        asm = foo.inspect_asm()

        # Function name in PTX
        self.assertIn("foo", asm)
        # NVVM inserted comments in PTX
        self.assertIn("Generated by NVIDIA NVVM Compiler", asm)

    def test_polytyped(self):
        @cuda.jit
        def foo(x, y):
            pass

        foo[1, 1](1, 1)
        foo[1, 1](1.2, 2.4)

        file = StringIO()
        foo.inspect_types(file=file)
        typeanno = file.getvalue()
        file.close()
        # Signature in annotation
        self.assertIn("({0}, {0})".format(intp), typeanno)
        self.assertIn("(float64, float64)", typeanno)

        # Signature in LLVM dict
        llvmirs = foo.inspect_llvm()
        self.assertEqual(2, len(llvmirs), )
        self.assertIn((self.cc, (intp, intp)), llvmirs)
        self.assertIn((self.cc, (float64, float64)), llvmirs)

        # Function name in LLVM
        self.assertIn("foo", llvmirs[self.cc, (intp, intp)])
        self.assertIn("foo", llvmirs[self.cc, (float64, float64)])

        asmdict = foo.inspect_asm()

        # Signature in LLVM dict
        self.assertEqual(2, len(asmdict), )
        self.assertIn((self.cc, (intp, intp)), asmdict)
        self.assertIn((self.cc, (float64, float64)), asmdict)

        # NNVM inserted in PTX
        self.assertIn("foo", asmdict[self.cc, (intp, intp)])
        self.assertIn("foo", asmdict[self.cc, (float64, float64)])

    def _test_inspect_sass(self, kernel, name, sass):
        # Ensure function appears in output
        seen_function = False
        for line in sass.split():
            if '.text' in line and name in line:
                seen_function = True
        self.assertTrue(seen_function)

        # Some instructions common to all supported architectures that should
        # appear in the output
        self.assertIn('S2R', sass)   # Special register to register
        self.assertIn('BRA', sass)   # Branch
        self.assertIn('EXIT', sass)  # Exit program

    @skip_without_nvdisasm('nvdisasm needed for inspect_sass()')
    def test_inspect_sass_eager(self):
        @cuda.jit((float32[::1], int32[::1]))
        def add(x, y):
            i = cuda.grid(1)
            if i < len(x):
                x[i] += y[i]

        self._test_inspect_sass(add, 'add', add.inspect_sass())

    @skip_without_nvdisasm('nvdisasm needed for inspect_sass()')
    def test_inspect_sass_lazy(self):
        @cuda.jit
        def add(x, y):
            i = cuda.grid(1)
            if i < len(x):
                x[i] += y[i]

        x = np.arange(10).astype(np.int32)
        y = np.arange(10).astype(np.float32)
        add[1, 10](x, y)

        signature = (int32[::1], float32[::1])
        self._test_inspect_sass(add, 'add', add.inspect_sass(signature))

    @skip_with_nvdisasm('Missing nvdisasm exception only generated when it is '
                        'not present')
    def test_inspect_sass_nvdisasm_missing(self):
        @cuda.jit((float32[::1],))
        def f(x):
            x[0] = 0

        with self.assertRaises(RuntimeError) as raises:
            f.inspect_sass()

        self.assertIn('nvdisasm is required', str(raises.exception))


if __name__ == '__main__':
    unittest.main()
