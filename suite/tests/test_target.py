import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
s = importlib.util.spec_from_file_location('hsd', Path(__file__).resolve().parents[1] / 'helper/hsd.py')
b = importlib.util.module_from_spec(s)
s.loader.exec_module(b)

def conn(port=3724, ip='192.0.2.1', host='', proc='/Applications/Hearthstone/Hearthstone.app/Contents/MacOS/Hearthstone', identity='game'):
    return {'id': identity, 'metadata': dict(network='tcp', destinationPort=str(port), destinationIP=ip, host=host, processPath=proc)}

class TargetTests(unittest.TestCase):
    def test_parse_ports_and_latest_target(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Power.log'
            n=p.with_name('GameNetLogger.log')
            for port in [1119,3724,45678]:
                n.write_text(f'Network.GotoGameServe() - address= 192.0.2.1:{port}, game=1\n')
                self.assertEqual(b.last_server_endpoint(p), ('192.0.2.1',port))
            with n.open('a') as f: f.write('Network.GotoGameServe() - address= 192.0.2.2:1234, game=2\n')
            self.assertEqual(b.last_server_endpoint(p), ('192.0.2.2',1234))
            with n.open('a') as f: f.write('Network.DisconnectFromGameServer() - Reason: EndGameScreen\n')
            self.assertIsNone(b.last_server_endpoint(p))
            with n.open('a') as f: f.write('Network.GotoGameServe() - address= 192.0.2.3:3724, reconnecting=True\n')
            self.assertEqual(b.last_server_endpoint(p), ('192.0.2.3',3724))
    def test_missing_and_invalid_logs(self):
        self.assertIsNone(b.last_server_endpoint(None))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Power.log'
            self.assertIsNone(b.last_server_endpoint(p))
            for address in ['999.0.0.1:3724','192.0.2.1:0','192.0.2.1:65536']:
                p.with_name('GameNetLogger.log').write_text('Network.GotoGameServe() - address= '+address)
                self.assertIsNone(b.last_server_endpoint(p))
    def select(self, cs, endpoint=('192.0.2.1',3724)):
        with patch.object(b,'last_server_endpoint',return_value=endpoint), patch.object(b,'clash_connections',return_value=cs):
            return b.hs_connections()
    def test_exact_match_preserves_login_other_process_and_old_server(self):
        game=conn()
        self.assertEqual(self.select([conn(port=1119,host='cn.actual.battlenet.com.cn'),conn(proc='/Other'),conn(port=1119),conn(ip='192.0.2.2'),conn(host='login.invalid'),game]),[game])
    def test_no_target_or_duplicates_fail_closed(self):
        self.assertEqual(self.select([conn()],None),[])
        self.assertEqual(self.select([conn(),conn(identity='duplicate')]),[])
        self.assertEqual(self.select([conn(port=1119)]),[])
    def test_only_exact_selected_id_deleted(self):
        with patch.object(b,'last_server_endpoint',return_value=('192.0.2.1',3724)), patch.object(b,'clash_connections',return_value=[conn(),conn(port=1119)]), patch.object(b,'clash_request') as request:
            self.assertEqual(b.cut_once(0),1)
            request.assert_called_once_with('DELETE','/connections/game')

if __name__=='__main__': unittest.main()
