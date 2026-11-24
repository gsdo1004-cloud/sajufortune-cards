import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts import threads_card_assets as a
import zodiac_cardnews as z
from PIL import Image
DAY='2026-11-25'

class AssetGate(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
        self.src=self.root/'cards'/DAY;self.src.mkdir(parents=True)
        self.rev=self.root/a.REVIEW;self.rev.parent.mkdir(parents=True)
        self.names=a.expected_names('reviewed_png')
        for i,n in enumerate(self.names): (self.src/n).write_bytes(f'reviewed-card-{i}'.encode())
        self.entry={'date':DAY,'source':'legacy_canonical_png','review':'visual_12_signs_complete','sha256':{n:a.file_hash(self.src/n) for n in self.names}}
        self.rev.write_text(json.dumps({DAY:self.entry}));self.img=patch.object(a,'safe_image');self.img.start();self.addCleanup(self.img.stop)
    def prep(self):return a.prepare(DAY,self.root)
    def test_exact_copy_and_no_canonical_change(self):
        before={p.name:p.read_bytes() for p in self.src.iterdir()};paths=self.prep()
        self.assertEqual(len(paths),4);self.assertEqual(before,{p.name:p.read_bytes() for p in self.src.iterdir()})
        self.assertEqual([a.file_hash(p) for p in paths],list(self.entry['sha256'].values()))
        self.assertEqual(paths,self.prep())
    def test_tampered_review_holds(self):
        (self.src/self.names[0]).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'review hash mismatch'):self.prep()
        self.assertFalse((self.root/'threads_cards'/DAY).exists())
    def test_missing_review_page_holds(self):
        (self.src/self.names[0]).unlink()
        with self.assertRaisesRegex(ValueError,'inventory'):self.prep()
    def test_mixed_jpg_holds_reviewed_route(self):
        (self.src/'card_01.jpg').write_bytes(b'mixed')
        with self.assertRaisesRegex(ValueError,'inventory'):self.prep()
    def test_extra_optional_not_copied(self):
        (self.src/'card_05.png').write_bytes(b'unreviewed optional')
        self.assertEqual([p.name for p in self.prep()],self.names)
    def test_flux_marker_holds(self):
        (self.src/'flux_backgrounds_applied.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'FLUX'):self.prep()
    def test_flux_dir_holds_review(self):
        (self.root/'assets/flux_daily'/DAY).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'FLUX'):self.prep()
    def test_signed_gate_holds(self):
        p=self.root/'scripts/zodiac_publish_guard.py';p.parent.mkdir();p.write_text('')
        with self.assertRaisesRegex(ValueError,'signed PR25'):self.prep()
    def test_existing_receipt_holds(self):
        (self.src/'threads_pub_carousel.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'already published'):self.prep()
    def test_isolated_file_mutation_holds(self):
        paths=self.prep();paths[0].write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'asset hash mismatch'):a.verify(DAY,self.root)
    def test_unreviewed_source_uses_only_static_renderer(self):
        self.rev.unlink();before={p.name:p.read_bytes() for p in self.src.iterdir()}
        def build(day,*,output_dir,legacy_only):
            self.assertEqual(day,DAY);self.assertTrue(legacy_only)
            for i,n in enumerate(a.expected_names('static_jpeg')):(output_dir/n).write_bytes(f'static-{i}'.encode())
        with patch('zodiac_cardnews_tpl.build',side_effect=build):paths=self.prep()
        self.assertEqual(len(paths),6);self.assertEqual(before,{p.name:p.read_bytes() for p in self.src.iterdir()})
    def test_partial_render_leaves_no_target(self):
        self.rev.unlink()
        with patch('zodiac_cardnews_tpl.build',side_effect=RuntimeError('render failed')):
            with self.assertRaises(RuntimeError):self.prep()
        self.assertFalse((self.root/'threads_cards'/DAY).exists())
    def test_public_exact_bytes_and_pinned_url(self):
        paths=self.prep()
        def get(url,**kwargs):
            p=next(p for p in paths if url.endswith('/'+p.name));r=MagicMock();r.__enter__.return_value=r;r.iter_content.return_value=[p.read_bytes()];return r
        with patch.object(a.requests,'get',side_effect=get) as remote:
            urls=a.public_urls(DAY,'a'*40,self.root);self.assertEqual(len(urls),4);self.assertEqual(remote.call_count,4)
        self.assertTrue(all('/'+'a'*40+'/' in url for url in urls))
    def test_public_mutation_holds(self):
        self.prep();r=MagicMock();r.__enter__.return_value=r;r.iter_content.return_value=[b'wrong']
        with patch.object(a.requests,'get',return_value=r):
            with self.assertRaisesRegex(ValueError,'remote bytes differ'):a.public_urls(DAY,'a'*40,self.root)
    def test_missing_pin_holds(self):
        with self.assertRaisesRegex(ValueError,'immutable'):a.public_urls(DAY,'main',self.root)
    def test_scoped_publisher_uses_isolated_gate(self):
        with patch.dict('os.environ',{'THREADS_CARD_ASSET_MODE':'isolated_v1','THREADS_CARD_ASSET_COMMIT':'a'*40}),patch.object(a,'public_urls',return_value=['verified']) as call:
            self.assertEqual(z._verified_image_urls(DAY),['verified']);call.assert_called_once()

class RealImageChecks(unittest.TestCase):
    def test_reject_wrong_dimensions_and_blank(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'card.png';Image.effect_noise((500,600),90).convert('RGB').save(p)
            with self.assertRaises(ValueError):a.safe_image(p,'PNG')
            Image.new('RGB',(1080,1920),'white').save(p)
            with self.assertRaises(ValueError):a.safe_image(p,'PNG')
    def test_legacy_renderer_never_resolves_flux(self):
        import zodiac_cardnews_tpl as t
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);folder=base/'set01';folder.mkdir();Image.new('RGB',(1080,1920),'gray').save(folder/'01_표지.jpg')
            with patch.object(t,'SETS_DIR',base),patch('scripts.flux_first_card_assets.background_path_for',side_effect=AssertionError('must not select FLUX')):
                self.assertEqual(t.bg(1,'01_표지',DAY,legacy_only=True).size,(1080,1920))
if __name__=='__main__':unittest.main()
