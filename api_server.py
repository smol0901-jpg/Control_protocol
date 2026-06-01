import threading
from flask import Flask, request, jsonify
from werkzeug.serving import make_server

class APIServer:
    def __init__(self, dev_cleaner_app, host='127.0.0.1', port=5050):
        self.app = Flask(__name__)
        self.dev_app = dev_cleaner_app
        self.host = host
        self.port = port
        self._setup_routes()
        self.httpd = None
        self.server_thread = None
        self._running = False

    def _require_auth(self, f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not token:
                token = request.args.get('token', '')
            user = self.dev_app.auth_system.validate_session(token)
            if not user:
                return jsonify({'error': 'Unauthorized'}), 401
            return f(*args, **kwargs)
        return decorated

    def _setup_routes(self):
        @self.app.route('/api/login', methods=['POST'])
        def login():
            data = request.get_json() or {}
            username = data.get('username', '')
            password = data.get('password', '')
            token = self.dev_app.auth_system.login(username, password)
            if token:
                return jsonify({'token': token})
            return jsonify({'error': 'Invalid credentials'}), 401

        @self.app.route('/api/processes', methods=['GET'])
        @self._require_auth
        def get_processes():
            procs = self.dev_app.monitor.scan_processes()
            result = [{
                'pid': p['pid'],
                'name': p['name'],
                'memory_mb': p['memory_mb'],
                'cpu_percent': p.get('cpu_percent', 0),
                'safe_to_kill': p.get('safe_to_kill', False),
                'confidence': p.get('confidence', 0)
            } for p in procs]
            return jsonify({'processes': result})

        @self.app.route('/api/kill/<int:pid>', methods=['POST'])
        @self._require_auth
        def kill_process(pid):
            success, message = self.dev_app.monitor.kill_process(pid)
            return jsonify({'success': success, 'message': message})

        @self.app.route('/api/kill_all', methods=['POST'])
        @self._require_auth
        def kill_all_safe():
            killed = 0
            for proc in self.dev_app.monitor.scan_processes():
                if proc.get('confidence', 0) > 0.8:
                    ok, _ = self.dev_app.monitor.kill_process(proc['pid'])
                    if ok:
                        killed += 1
            return jsonify({'killed': killed})

        @self.app.route('/api/clean_cache', methods=['POST'])
        @self._require_auth
        def clean_cache():
            total_mb, details = self.dev_app.clean_all_caches()
            return jsonify({'freed_mb': total_mb, 'details': details})

        @self.app.route('/api/stats', methods=['GET'])
        @self._require_auth
        def get_stats():
            sys_stats = self.dev_app._get_system_stats()
            app_stats = self.dev_app.stats.copy()
            ml_stats = self.dev_app.analyzer.get_model_stats()
            return jsonify({'system': sys_stats, 'app': app_stats, 'ml': ml_stats})

        @self.app.route('/api/report', methods=['GET'])
        @self._require_auth
        def generate_report():
            report_type = request.args.get('type', 'daily')
            try:
                pdf_path = self.dev_app.generate_report(report_type)
                return jsonify({'status': 'created', 'path': str(pdf_path)})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/hud/start', methods=['POST'])
        @self._require_auth
        def start_hud():
            if not self.dev_app.config.get('hud_enabled', False):
                self.dev_app.toggle_hud()
            return jsonify({'hud': 'started' if self.dev_app.config['hud_enabled'] else 'error'})

        @self.app.route('/api/hud/stop', methods=['POST'])
        @self._require_auth
        def stop_hud():
            if self.dev_app.config.get('hud_enabled', False):
                self.dev_app.toggle_hud()
            return jsonify({'hud': 'stopped' if not self.dev_app.config['hud_enabled'] else 'error'})

        @self.app.route('/api/config', methods=['GET', 'PUT'])
        @self._require_auth
        def config():
            if request.method == 'GET':
                return jsonify(self.dev_app.config)
            elif request.method == 'PUT':
                new_config = request.get_json()
                if new_config:
                    self.dev_app.config.update(new_config)
                    self.dev_app._save_config()
                return jsonify({'status': 'updated'})

    def start(self):
        if self._running:
            return
        self.httpd = make_server(self.host, self.port, self.app)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()
        self._running = True

    def shutdown(self):
        if self.httpd and self._running:
            self.httpd.shutdown()
            self._running = False
            self.server_thread = None
