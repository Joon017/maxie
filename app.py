# app.py - Main Flask Application
from flask import Flask, render_template
from api.events import events_bp
from api.layers import layers_bp
from api.tasks import tasks_bp
from api.recurring_patterns import patterns_bp
from utils.data_manager import ensure_data_directory

def create_app():
    app = Flask(__name__)
    
    # Ensure data directory exists
    ensure_data_directory()
    
    # Register blueprints
    app.register_blueprint(events_bp, url_prefix='/api')
    app.register_blueprint(layers_bp, url_prefix='/api')
    app.register_blueprint(tasks_bp, url_prefix='/api')
    app.register_blueprint(patterns_bp, url_prefix='/api')
    
    # Main route
    @app.route('/')
    def index():
        return render_template('index.html')
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)