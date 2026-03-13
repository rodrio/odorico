# Gunicorn configuration file for Odorico application
import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"
backlog = 2048

# Worker processes
workers = int(os.environ.get('WEB_CONCURRENCY', 3))
worker_class = 'sync'
worker_connections = 1000
timeout = 120
keepalive = 2

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'odorico'

# Server mechanics
daemon = False
pidfile = '/tmp/gunicorn.pid'
user = None
group = None
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None

# Monitoring
statsd_host = None
statsd_prefix = ''

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Server is starting...")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Server is reloading...")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Server is ready.")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    worker.log.info(f"Worker initialized (pid: {worker.pid})")

def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info(f"Worker exited (pid: {worker.pid})")

def child_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info(f"Child worker exited (pid: {worker.pid})")

def on_exit(server):
    """Called just before exiting."""
    server.log.info("Server is shutting down...")

def worker_abort(worker):
    """Called when a worker failed to boot."""
    worker.log.info(f"Worker failed to boot (pid: {worker.pid})")
