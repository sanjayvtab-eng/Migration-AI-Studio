"""Isolated loopback-only smoke test; no connector registration or source access."""
import importlib.util, socket, urllib.request
from pathlib import Path
spec=importlib.util.spec_from_file_location('agent',Path(__file__).parents[1]/'scripts/local_connector.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
held=[]
try:
    for port in [*range(8585,8600),38585,48585,58585]:
        listener=socket.socket()
        try:listener.bind(('127.0.0.1',port));listener.listen();held.append(listener)
        except OSError:listener.close()  # Already occupied, which is the tested condition.
    port=agent.start_dashboard_server(8585)
    assert port and port not in [*range(8585,8600),38585,48585,58585]
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status',timeout=5) as response:
        assert response.status==200
    print(f'PASS: occupied preferred ports; ephemeral loopback dashboard reachable on {port}')
finally:
    for listener in held:listener.close()
