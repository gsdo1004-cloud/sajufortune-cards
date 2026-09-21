import unittest,xml.etree.ElementTree as ET
import threads_mobile_consumer as m
class T(unittest.TestCase):
 def root(self,txt='',submit=True):
  s=f'''<hierarchy><node class="android.widget.EditText" resource-id="permalink_inline_composer" text="{txt}" bounds="[60,1818][744,2142]" clickable="true"/><node class="android.view.View" text="" bounds="[912,1908][1056,2052]" clickable="{'true' if submit else 'false'}"/></hierarchy>'''; return ET.fromstring(s)
 def test_exact(self): self.assertTrue(m.exact(self.root('abc'),'abc'))
 def test_exact_fail(self): self.assertFalse(m.exact(self.root('ab'),'abc'))
 def test_submit_signature(self): self.assertIsNotNone(m.submit_control(self.root('abc')))
 def test_receipt(self): self.assertTrue(m.receipt(ET.fromstring('<h><n text="acct"/><n text="hello"/></h>'),'acct','hello'))
 def test_receipt_fail(self): self.assertFalse(m.receipt(ET.fromstring('<h><n text="hello"/></h>'),'acct','hello'))
if __name__=='__main__': unittest.main()
