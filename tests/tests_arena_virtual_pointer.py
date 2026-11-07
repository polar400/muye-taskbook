"""No-process-IO tests for the proposed arena virtual pointer."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock,patch
import arena_virtual_pointer as virtual


class Memory:
    def __init__(self):self.values={100:b'old1',200:b'old2'};self.fail_after_write=None
    def read(self,address,size):return self.values[address]
    def replace(self,address,expected,data):
        if self.values[address]!=expected:raise RuntimeError('conflict')
        self.values[address]=data
        if self.fail_after_write==address and data.startswith(b'new'):
            self.fail_after_write=None;raise RuntimeError('uncertain write')


def run_stub(code,argument,clock=100):
    """Evaluate the tiny emitted x86 functions, including stdcall stack cleanup."""
    ip=0;eax=0;zero=False;carry=False;memory={}
    for _ in range(30):
        if code[ip:ip+4]==b'\x8b\x44\x24\x04':eax=argument;ip+=4
        elif code[ip:ip+2]==b'\x85\xc0':zero=eax==0;ip+=2
        elif code[ip]==0x74:ip+=2+(code[ip+1] if zero else 0)
        elif code[ip:ip+2]==b'\xc7\x00':memory[eax]=struct.unpack_from('<i',code,ip+2)[0];ip+=6
        elif code[ip:ip+3]==b'\xc7\x40\x04':memory[eax+4]=struct.unpack_from('<i',code,ip+3)[0];ip+=7
        elif code[ip]==0xb8:eax=struct.unpack_from('<I',code,ip+1)[0];ip+=5
        elif code[ip:ip+2]==b'\xff\xd0':
            if eax!=0x1234:raise AssertionError('Unexpected indirect API call')
            eax=clock;ip+=2
        elif code[ip]==0x2d:eax=(eax-struct.unpack_from('<I',code,ip+1)[0])&0xffffffff;ip+=5
        elif code[ip]==0x3d:carry=eax<struct.unpack_from('<I',code,ip+1)[0];ip+=5
        elif code[ip]==0x72:ip+=2+(code[ip+1] if carry else 0)
        elif code[ip:ip+2]==b'\xff\xe0':return ('original',eax),None,memory
        elif code[ip:ip+2]==b'\x31\xc0':eax=0;ip+=2
        elif code[ip]==0xc2:return eax,struct.unpack_from('<H',code,ip+1)[0],memory
        else:raise AssertionError('Unexpected x86 instruction')
    raise AssertionError('Stub did not return')


class VirtualPointerTests(unittest.TestCase):
    def stubs(self,x,y,hwnd,started=100):
        return virtual.pointer_stubs(x,y,hwnd,clock=0x1234,started=started,
                                     original_cursor=0x5678,original_hit=0x6789)

    def transaction(self):
        memory=Memory();entries=[(100,b'old1',b'new1'),(200,b'old2',b'new2')]
        return memory,virtual.PointerTransaction(memory,entries)

    def test_two_imports_are_restored_after_normal_exit(self):
        memory,transaction=self.transaction()
        with transaction:self.assertEqual(memory.values,{100:b'new1',200:b'new2'})
        self.assertEqual(memory.values,{100:b'old1',200:b'old2'})

    def test_capture_error_restores_both_imports(self):
        memory,transaction=self.transaction()
        with self.assertRaisesRegex(RuntimeError,'capture failed'):
            with transaction:raise RuntimeError('capture failed')
        self.assertEqual(memory.values,{100:b'old1',200:b'old2'})

    def test_uncertain_second_write_rolls_back_both_slots(self):
        memory,transaction=self.transaction();memory.fail_after_write=200
        with self.assertRaisesRegex(RuntimeError,'uncertain'):transaction.start()
        self.assertEqual(memory.values,{100:b'old1',200:b'old2'})

    def test_concurrent_change_is_not_overwritten_and_other_slot_restores(self):
        memory,transaction=self.transaction();transaction.start();memory.values[200]=b'else'
        with self.assertRaisesRegex(RuntimeError,'恢复失败'):transaction.stop()
        self.assertEqual(memory.values,{100:b'old1',200:b'else'})

    def test_double_start_is_rejected(self):
        memory,transaction=self.transaction();transaction.start()
        with self.assertRaisesRegex(RuntimeError,'重复'):transaction.start()
        transaction.stop();self.assertEqual(memory.values,{100:b'old1',200:b'old2'})

    def test_cursor_stub_writes_signed_coordinates_and_returns_success(self):
        cursor,hit=self.stubs(-120,615,329392)
        self.assertEqual(run_stub(cursor,0x10000),(1,4,{0x10000:-120,0x10004:615}))
        self.assertEqual(run_stub(hit,0),(329392,8,{}))

    def test_null_point_returns_false_without_writing(self):
        cursor,_=self.stubs(480,410,329392)
        self.assertEqual(run_stub(cursor,0),(0,4,{}))

    def test_expiry_uses_original_apis_even_without_python_cleanup(self):
        cursor,hit=self.stubs(480,410,329392)
        self.assertEqual(run_stub(cursor,0x10000,5099),(1,4,{0x10000:480,0x10004:410}))
        self.assertEqual(run_stub(cursor,0x10000,5100),(('original',0x5678),None,{}))
        self.assertEqual(run_stub(hit,0,5100),(('original',0x6789),None,{}))

    def test_clock_wraparound_does_not_extend_five_second_expiry(self):
        cursor,_=self.stubs(-100,615,329392,started=0xfffffff0)
        self.assertEqual(run_stub(cursor,0x10000,10),(1,4,{0x10000:-100,0x10004:615}))
        self.assertEqual(run_stub(cursor,0x10000,4984),(('original',0x5678),None,{}))

    def test_missing_authorization_never_opens_any_process(self):
        with tempfile.TemporaryDirectory(prefix='arena-virtual-auth-',dir=Path(__file__).resolve().parents[1]/'verification') as path:
            window=Mock()
            with patch.object(virtual,'ROOT',Path(path)),patch.object(virtual.ctypes,'WinDLL') as loader:
                with self.assertRaisesRegex(RuntimeError,'尚未获准'):virtual.ArenaVirtualPointer(window)
                loader.assert_not_called();window.check.assert_not_called()

    def test_consumed_once_authorization_cannot_open_native_apis(self):
        with tempfile.TemporaryDirectory(prefix='arena-virtual-auth-',dir=Path(__file__).resolve().parents[1]/'verification') as folder:
            root=Path(folder);(root/'verification').mkdir()
            for name in ('arena-virtual-pointer-authorization-20261020.json','arena-lower-virtual-authorization-20261020.json'):
                (root/'verification'/name).write_text('{"decision":"consumed","remaining":0}',encoding='utf-8')
            with patch.object(virtual,'ROOT',root),patch.object(virtual.ctypes,'WinDLL') as loader:
                with self.assertRaisesRegex(RuntimeError,'尚未获准'):virtual.ArenaVirtualPointer(Mock())
                with self.assertRaisesRegex(RuntimeError,'尚未获准'):virtual.ArenaVirtualPointer(Mock(),purpose='lower-once')
                loader.assert_not_called()


if __name__=='__main__':unittest.main()
