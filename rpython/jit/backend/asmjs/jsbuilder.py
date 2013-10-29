
from rpython.rtyper.lltypesystem import lltype, rffi
from rpython.jit.metainterp.history import (ConstInt, ConstFloat, ConstPtr,
                                            TargetToken)

from rpython.jit.backend.asmjs import jsvalue as jsval
from rpython.jit.backend.asmjs.arch import SANITYCHECK


class ASMJSBuilder(object):
    """Class for building ASMJS assembly of a trace.

    This class can be used to build up the source for a single-function ASMJS
    module.  The structure of the code is optimized for a labelled trace with
    a single jump backwards at the end.  It renders the code as a prelude
    followed by a single while-loop. Jumps into labeled points in the code are
    facilitated by conditionals and an input argument named "goto":

        function (jitframe, goto) {
          if (goto <= 0) {
            <block zero>
          }
          ...
          if (goto <= M) {
            <block M>
          }
          while(true) {
            if (goto <= M+1) {
              <block M+1>
            }
            ...
            if (goto <= N) {
              <block N>
            }
            goto = 0;
            continue
          }
        }

    According to the emscripten technical paper, it is quite important to use
    high-level control-flow structures rather than a more general switch-in-
    a-loop.  An alternative would be to import and use the whole emscripten
    relooper algorithm, but that sounds painful and expensive.

    XXX TODO: is this too general, or too broad?  try to do better!
    XXX TODO: benchmark against a generic switch-in-a-loop construct.

    The compiled function always returns an integer.  If it returns zero then
    execution has completed.  If it returns a positive integer, this identifies
    another compiled function into which execution should jump.  We expect to
    be run inside some sort of trampoline that can execute these jumps without
    blowing the call stack.

    XXX TODO: produce more concise code once we're sure it's working,
              e.g. by removing newlines and semicolons.
    """

    def __init__(self, cpu):
        self.cpu = cpu
        self.source_chunks = []
        self.all_intvars = {}
        self.all_doublevars = {}
        self.free_intvars = []
        self.free_doublevars = []
        self.token_labels = {}
        self.loop_entry_token = None
        self.imported_functions = {}

    def finish(self):
        return "".join(self._build_prelude() +
                       self.source_chunks +
                       self._build_epilog())

    def _build_prelude(self):
        chunks = []
        # Standard asmjs prelude stuff.
        chunks.append('function(stdlib, foreign, heap){\n')
        chunks.append('"use asm";\n')
        chunks.append('var HI8 = new stdlib.Int8Array(heap);\n')
        chunks.append('var HI16 = new stdlib.Int16Array(heap);\n')
        chunks.append('var HI32 = new stdlib.Int32Array(heap);\n')
        chunks.append('var HU8 = new stdlib.Uint8Array(heap);\n')
        chunks.append('var HU16 = new stdlib.Uint16Array(heap);\n')
        chunks.append('var HU32 = new stdlib.Uint32Array(heap);\n')
        chunks.append('var HF32 = new stdlib.Float32Array(heap);\n')
        chunks.append('var HF64 = new stdlib.Float64Array(heap);\n')
        chunks.append('var imul = stdlib.Math.imul;\n')
        # Import any required names from the Module object.
        chunks.append('var tempDoublePtr = foreign.tempDoublePtr|0;\n')
        for funcname in self.imported_functions:
            chunks.append('var %s = foreign.%s;\n' % (funcname, funcname))
        # The function definition, including variable declarations.
        chunks.append('function F(jitframe, goto){\n')
        chunks.append('jitframe=jitframe|0;\n')
        chunks.append('goto=goto|0;\n')
        for varname, init_int in self.all_intvars.iteritems():
            chunks.append("var %s=%d;\n" % (varname, init_int))
        for varname, init_double in self.all_doublevars.iteritems():
            chunks.append("var %s=%f;\n" % (varname, init_double))
        chunks.append("if((goto|0) <= (0|0)){\n")
        return chunks

    def _build_epilog(self):
        chunks = []
        # End the final labelled block.
        chunks.append("}\n")
        # End the loop, if we're in one.
        if self.loop_entry_token is not None:
            chunks.append("goto = 0|0;\n")
            chunks.append("}\n")
        # The compiled function always returns zero when it's finished.
        chunks.append('return 0;\n')
        chunks.append('}\n')
        # Export the singleton compiled function.
        chunks.append('return F;\n')
        chunks.append('}\n')
        return chunks

    def allocate_intvar(self):
        """Allocate a variable of type int.

        If there is a previously-freed variable of appropriate type then
        that variable is re-used; otherwise a fresh variable name is
        allocated and emitted.
        """
        if len(self.free_intvars) > 0:
            varname = self.free_intvars.pop()
        else:
            varname = "i%d" % (len(self.all_intvars),)
            self.all_intvars[varname] = 0
        return jsval.IntVar(varname)

    def allocate_doublevar(self):
        """Allocate a variable of type double.

        If there is a previously-freed variable of appropriate type then
        that variable is re-used; otherwise a fresh variable name is
        allocated and emitted.
        """
        if len(self.free_doublevars) > 0:
            varname = self.free_doublevars.pop()
        else:
            varname = "f%d" % (len(self.all_doublevars),)
            self.all_doublevars[varname] = 0
        return jsval.DoubleVar(varname)

    def free_intvar(self, var):
        """Free up the given int variable for future re-use."""
        assert isinstance(var, jsval.IntVar)
        self.free_intvars.append(var.varname)

    def free_doublevar(self, var):
        """Free up the given double variable for future re-use."""
        assert isinstance(var, jsval.DoubleVar)
        self.free_doublevars.append(var.varname)

    def set_initial_value_intvar(self, var, value):
        """Set the initial value of an integer variable."""
        assert isinstance(var, jsval.IntVar)
        self.all_intvars[var.varname] = value

    def set_initial_value_doublevar(self, var, value):
        """Set the initial value of an integer variable."""
        assert isinstance(var, jsval.DoubleVar)
        self.all_doublevars[var.varname] = value

    def set_loop_entry_token(self, token):
        """Indicate which token is the target of the final JUMP operation.

        If the trace being compiled ends in a JUMP operation, this method
        should be called to indicate the target of that jump.  It causes the
        generated code to contain an appropriate loop statement.
        """
        assert self.loop_entry_token is None
        self.loop_entry_token = token

    def emit_token_label(self, token):
        """Emit a label indicating the start of this token's block.

        This function can be be used to split up the generated code into
        distinct labelled blocks.  It returns an integer identifying the
        label for the token; passing this integer as the 'goto' argument
        will jump control directly to that label.
        """
        assert isinstance(token, TargetToken)
        # Close the previous block.
        self.emit("}\n")
        # If this is the loop token, enter the loop.
        if token == self.loop_entry_token:
            self.emit("while(1){\n")
        # Assign a label and begin the new block.
        label = len(self.token_labels) + 1
        self.token_labels[token] = label
        self.emit("if((goto|0) <= (%d|0)){\n" % (label,))
        return label

    def emit(self, code):
        """Emit the given string directly into the generated code."""
        self.source_chunks.append(code)

    def emit_statement(self, code):
        """Emit the given string as a statement into.

        This sanity-checks and appends an appropriate statement terminator.
        """
        self.emit(code)
        if code.endswith("}"):
            self.emit("\n")
        else:
            self.emit(";\n")

    def emit_value(self, val):
        """Emit a reference to a ASMJSValue in the generated source."""
        if val is None:
            self.emit_value(jsval.zero)
        elif isinstance(val, jsval.ASMJSValue):
            val.emit_value(self)
        elif isinstance(val, ConstInt):
            intval = (rffi.cast(lltype.Signed, val.getint()))
            self.emit(str(intval))
        elif isinstance(val, ConstPtr):
            refval = (rffi.cast(lltype.Signed, val.getref_base()))
            self.emit(str(refval))
        elif isinstance(val, ConstFloat):
            self.emit(str(val.getfloat()))
        else:
            raise RuntimeError("Unknown js value type: %s" % (val,))

    def emit_expr(self, val):
        self.emit_value(val)
        self.emit(";\n")

    def emit_assignment(self, target, value):
        """Emit an assignment of a value to the given target."""
        assert isinstance(target, jsval.Variable)
        self.emit(target.varname)
        self.emit("=")
        if jsval.istype(target, jsval.Double):
            if not jsval.istype(value, jsval.Double):
                self.emit("+")
        self.emit("(")
        self.emit_value(value)
        self.emit(")")
        if jsval.istype(target, jsval.Int):
            if not jsval.istype(value, jsval.Int):
                self.emit("|0")
        self.emit(";\n")

    def emit_load(self, target, addr, typ):
        """Emit a typed load operation from the heap into a target.

        Given a result-storing target, a heap address, and an optional heap
        type, this method generates a generic "load from heap" instruction of
        the following form:

            target = HEAPVIEW[(addr) >> shift];

        """
        assert isinstance(addr, jsval.AbstractValue)
        # For doubles, we can't guarantee that the data is aligned.
        # Read it as two 32bit ints into a properly aligned chunk.
        if typ is jsval.Float64:
            tempaddr = self.allocate_intvar()
            self.emit_assignment(tempaddr, addr)
            addr = jsval.tempDoublePtr
            word1 = jsval.HeapData(jsval.Int32, tempaddr)
            self.emit_store(word1, addr, jsval.Int32)
            wordsize = ConstInt(4)
            word2 = jsval.HeapData(jsval.Int32, jsval.Plus(tempaddr, wordsize))
            self.emit_store(word2, jsval.Plus(addr, wordsize), jsval.Int32)
            self.free_intvar(tempaddr)
        # Now we can do the actual load.
        assert isinstance(target, jsval.Variable)
        self.emit(target.varname)
        self.emit("=")
        if jsval.istype(target, jsval.Double):
            self.emit("+")
        self.emit("(")
        self.emit(typ.heap_name)
        self.emit("[(")
        self.emit_value(addr)
        self.emit(")>>")
        self.emit(str(typ.shift))
        self.emit("])")
        if jsval.istype(target, jsval.Int):
            self.emit("|0")
        self.emit(";\n")

    def emit_store(self, value, addr, typ):
        """Emit a typed store operation of a value into the heap.

        Given a jsvalue, a heap address, and a HeapType, this method generates
        a generic "store to heap" instruction of the following form:

            HEAPVIEW[(addr) >> shift] = value;

        """
        assert isinstance(addr, jsval.AbstractValue)
        # For doubles, we can't guarantee that the data is aligned.
        # We have to store it into a properly aligned chunk, then
        # copy to final destination as two 32-bit ints.
        tempaddr = None
        if typ is jsval.Float64:
            tempaddr = self.allocate_intvar()
            self.emit_assignment(tempaddr, addr)
            addr = jsval.tempDoublePtr
        self.emit(typ.heap_name)
        self.emit("[(")
        self.emit_value(addr)
        self.emit(")>>")
        self.emit(str(typ.shift))
        self.emit("]=")
        self.emit_value(value)
        self.emit(";\n")
        if typ is jsval.Float64:
            word1 = jsval.HeapData(jsval.Int32, addr)
            self.emit_store(word1, tempaddr, jsval.Int32)
            wordsize = ConstInt(4)
            word2 = jsval.HeapData(jsval.Int32, jsval.Plus(addr, wordsize))
            self.emit_store(word2, jsval.Plus(tempaddr, wordsize), jsval.Int32)
            self.free_intvar(tempaddr)

    def emit_jump(self, token):
        """Emit a jump to the given token.

        For jumps to the loop-entry token of the current function, this just
        moves to the next iteration of the loop.  For other targets it looks
        up the compiled functionid and goto address, and returns that value
        to the trampoline.
        """
        assert isinstance(token, TargetToken)
        if token == self.loop_entry_token:
            # A local loop, just move to the next iteration.
            self.emit_statement("goto = 0|0")
            self.emit_statement("continue")
        else:
            # An external loop, need to goto via trampoline.
            self.emit_goto(token._asmjs_funcid, token._asmjs_label)

    def emit_goto(self, funcid, label=0):
        """Emit a goto to the funcid and label.

        Essentially we just encode the funcid and label into a single integer
        and return it.  We expect to be running inside some sort of trampoline
        that can actually execute the goto.
        """
        assert funcid < 2**24
        assert label < 0xFF
        next_call = (funcid << 8) | label
        self.emit_statement("return %d" % (next_call,))

    def emit_exit(self):
        """Emit an immediate return from the function."""
        self.emit("return 0;\n")

    def emit_comment(self, msg):
        self.emit("// %s\n" % (msg,))

    def emit_debug(self, msg, values=None):
        if SANITYCHECK:
            self.emit("log(\"%s\"" % (msg,))
            if values is not None:
                for value in values:
                    self.emit(",")
                    self.emit_value(value)
            self.emit(");\n")

    def emit_if_block(self, test):
        return ctx_if_block(self, test)

    def emit_else_block(self):
        return ctx_else_block(self)


class ctx_if_block(object):

    def __init__(self, js, test):
        self.js = js
        if not jsval.istype(test, jsval.Int):
            test = jsval.IntCast(test)
        self.test = test

    def __enter__(self):
        self.js.emit("if(")
        self.js.emit_value(self.test)
        self.js.emit("){\n")
        return self.js

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.js.emit("}\n")


class ctx_else_block(object):

    def __init__(self, js):
        self.js = js

    def __enter__(self):
        self.js.emit("else {\n")
        return self.js

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.js.emit("}\n")
