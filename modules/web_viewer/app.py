#!/usr/bin/env python3
"""
MeshCore Bot Data Viewer
Bot montoring web interface using Flask-SocketIO 5.x
"""

import sqlite3
import json
import time
import configparser
import logging
import threading
from datetime import datetime, timedelta, date
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from pathlib import Path
import os
import sys
from typing import Dict, Any, Optional, List

# Add the project root to the path so we can import bot components
project_root = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, project_root)

from modules.db_manager import DBManager
from modules.repeater_manager import RepeaterManager

class BotDataViewer:
    """Complete web interface using Flask-SocketIO 5.x best practices"""
    
    def __init__(self, db_path="meshcore_bot.db", repeater_db_path=None, config_path="config.ini"):
        # Setup comprehensive logging
        self._setup_logging()
        
        self.app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
        self.app.config['SECRET_KEY'] = 'meshcore_bot_viewer_secret'
        
        # Flask-SocketIO configuration following 5.x best practices
        self.socketio = SocketIO(
            self.app, 
            cors_allowed_origins="*",
            max_http_buffer_size=1000000,  # 1MB buffer limit
            ping_timeout=5,                # 5 second ping timeout (Flask-SocketIO 5.x default)
            ping_interval=25,             # 25 second ping interval (Flask-SocketIO 5.x default)
            logger=False,                  # Disable verbose logging
            engineio_logger=False,        # Disable EngineIO logging
            async_mode='threading'        # Use threading for better stability
        )
        
        self.db_path = db_path
        self.repeater_db_path = repeater_db_path
        
        # Connection management using Flask-SocketIO built-ins
        self.connected_clients = {}  # Track client metadata
        self.max_clients = 10
        
        # Database connection pooling with thread safety
        self._db_connection = None
        self._db_lock = threading.Lock()
        self._db_last_used = 0
        self._db_timeout = 300  # 5 minutes connection timeout
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Initialize databases
        self._init_databases()
        
        # Setup routes and SocketIO handlers
        self._setup_routes()
        self._setup_socketio_handlers()
        
        # Start database polling for real-time data
        self._start_database_polling()
        
        # Start periodic cleanup
        self._start_cleanup_scheduler()
        
        self.logger.info("BotDataViewer initialized with Flask-SocketIO 5.x best practices")
    
    def _setup_logging(self):
        """Setup comprehensive logging"""
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Get or create logger (don't use basicConfig as it may conflict with existing logging)
        self.logger = logging.getLogger('modern_web_viewer')
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Create file handler
        file_handler = logging.FileHandler('logs/web_viewer_modern.log')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Prevent propagation to root logger to avoid duplicate messages
        self.logger.propagate = False
        
        self.logger.info("Web viewer logging initialized")
    
    def _load_config(self, config_path):
        """Load configuration from file"""
        config = configparser.ConfigParser()
        if os.path.exists(config_path):
            config.read(config_path)
        return config
    
    def _init_databases(self):
        """Initialize database connections"""
        try:
            # Initialize database manager for metadata access
            from modules.db_manager import DBManager
            # Create a minimal bot object for DBManager
            class MinimalBot:
                def __init__(self, logger, config, db_manager=None):
                    self.logger = logger
                    self.config = config
                    self.db_manager = db_manager
            
            # Create DBManager first
            minimal_bot = MinimalBot(self.logger, self.config)
            self.db_manager = DBManager(minimal_bot, self.db_path)
            
            # Now set db_manager on the minimal bot for RepeaterManager
            minimal_bot.db_manager = self.db_manager
            
            # Initialize repeater manager for geocoding functionality
            self.repeater_manager = RepeaterManager(minimal_bot)
            
            # Initialize packet_stream table for real-time monitoring
            self._init_packet_stream_table()
            
            # Store database paths for direct connection
            self.db_path = self.db_path
            self.repeater_db_path = self.repeater_db_path
            self.logger.info("Database connections initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize databases: {e}")
            raise
    
    def _init_packet_stream_table(self):
        """Initialize the packet_stream table in bot_data.db"""
        try:
            # Get database path from config
            db_path = self.config.get('Database', 'path', fallback='bot_data.db')
            
            # Connect to database and create table if it doesn't exist
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create packet_stream table with schema matching the INSERT statements
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS packet_stream (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    data TEXT NOT NULL,
                    type TEXT NOT NULL
                )
            ''')
            
            # Create index on timestamp for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_packet_stream_timestamp 
                ON packet_stream(timestamp)
            ''')
            
            # Create index on type for filtering by type
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_packet_stream_type 
                ON packet_stream(type)
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Initialized packet_stream table in {db_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize packet_stream table: {e}")
            # Don't raise - allow web viewer to continue even if table init fails
    
    def _get_db_connection(self):
        """Get database connection - create new connection for each request to avoid threading issues"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            self.logger.error(f"Failed to create database connection: {e}")
            raise
    
    def _setup_routes(self):
        """Setup all Flask routes - complete feature parity"""
        
        @self.app.route('/')
        def index():
            """Main dashboard"""
            return render_template('index.html')
        
        @self.app.route('/realtime')
        def realtime():
            """Real-time monitoring dashboard"""
            return render_template('realtime.html')
        
        @self.app.route('/contacts')
        def contacts():
            """Contacts page - unified contact management and tracking"""
            return render_template('contacts.html')
        
        @self.app.route('/cache')
        def cache():
            """Cache management page"""
            return render_template('cache.html')
        
        
        @self.app.route('/stats')
        def stats():
            """Statistics page"""
            return render_template('stats.html')
        
        
        # API Routes
        @self.app.route('/api/health')
        def api_health():
            """Health check endpoint"""
            # Get bot uptime
            bot_uptime = self._get_bot_uptime()
            
            return jsonify({
                'status': 'healthy',
                'connected_clients': len(self.connected_clients),
                'max_clients': self.max_clients,
                'timestamp': time.time(),
                'bot_uptime': bot_uptime,
                'version': 'modern_2.0'
            })
        
        @self.app.route('/api/stats')
        def api_stats():
            """Get comprehensive database statistics for dashboard"""
            try:
                stats = self._get_database_stats()
                return jsonify(stats)
            except Exception as e:
                self.logger.error(f"Error getting stats: {e}")
                return jsonify({'error': str(e)}), 500
        
        
        
        @self.app.route('/api/contacts')
        def api_contacts():
            """Get contact data"""
            try:
                contacts = self._get_tracking_data()
                return jsonify(contacts)
            except Exception as e:
                self.logger.error(f"Error getting contacts: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/cache')
        def api_cache():
            """Get cache data"""
            try:
                cache_data = self._get_cache_data()
                return jsonify(cache_data)
            except Exception as e:
                self.logger.error(f"Error getting cache: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/database')
        def api_database():
            """Get database information"""
            try:
                db_info = self._get_database_info()
                return jsonify(db_info)
            except Exception as e:
                self.logger.error(f"Error getting database info: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/optimize-database', methods=['POST'])
        def api_optimize_database():
            """Optimize database using VACUUM, ANALYZE, and REINDEX"""
            try:
                result = self._optimize_database()
                return jsonify(result)
            except Exception as e:
                self.logger.error(f"Error optimizing database: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        
        @self.app.route('/api/stream_data', methods=['POST'])
        def api_stream_data():
            """API endpoint for receiving real-time data from bot"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'No data provided'}), 400
                
                data_type = data.get('type')
                if data_type == 'command':
                    self._handle_command_data(data.get('data', {}))
                elif data_type == 'packet':
                    self._handle_packet_data(data.get('data', {}))
                else:
                    return jsonify({'error': 'Invalid data type'}), 400
                
                return jsonify({'status': 'success'})
            except Exception as e:
                self.logger.error(f"Error in stream_data endpoint: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/recent_commands')
        def api_recent_commands():
            """API endpoint to get recent commands from database"""
            try:
                import sqlite3
                import json
                import time
                
                # Get commands from last 60 minutes
                cutoff_time = time.time() - (60 * 60)  # 60 minutes ago
                
                # Get database path
                db_path = self.config.get('Database', 'path', fallback='bot_data.db')
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT data FROM packet_stream 
                    WHERE type = 'command' AND timestamp > ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                ''', (cutoff_time,))
                
                rows = cursor.fetchall()
                conn.close()
                
                # Parse and return commands
                commands = []
                for (data_json,) in rows:
                    try:
                        command_data = json.loads(data_json)
                        commands.append(command_data)
                    except Exception as e:
                        self.logger.debug(f"Error parsing command data: {e}")
                
                return jsonify({'commands': commands})
                
            except Exception as e:
                self.logger.error(f"Error getting recent commands: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/geocode-contact', methods=['POST'])
        def api_geocode_contact():
            """Manually geocode a contact by public_key"""
            try:
                data = request.get_json()
                if not data or 'public_key' not in data:
                    return jsonify({'error': 'public_key is required'}), 400
                
                public_key = data['public_key']
                
                # Get contact data from database
                conn = self._get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT latitude, longitude, name, city, state, country
                    FROM complete_contact_tracking
                    WHERE public_key = ?
                ''', (public_key,))
                
                contact = cursor.fetchone()
                if not contact:
                    conn.close()
                    return jsonify({'error': 'Contact not found'}), 404
                
                lat = contact['latitude']
                lon = contact['longitude']
                name = contact['name']
                
                # Check if we have valid coordinates
                if lat is None or lon is None or lat == 0.0 or lon == 0.0:
                    conn.close()
                    return jsonify({'error': 'Contact does not have valid coordinates'}), 400
                
                # Perform geocoding
                self.logger.info(f"Manual geocoding requested for {name} ({public_key[:16]}...) at coordinates {lat}, {lon}")
                # sqlite3.Row objects use dictionary-style access with []
                current_city = contact['city']
                current_state = contact['state']
                current_country = contact['country']
                self.logger.debug(f"Current location data - city: {current_city}, state: {current_state}, country: {current_country}")
                
                try:
                    location_info = self.repeater_manager._get_full_location_from_coordinates(lat, lon)
                    self.logger.debug(f"Geocoding result for {name}: {location_info}")
                except Exception as geocode_error:
                    conn.close()
                    self.logger.error(f"Exception during geocoding for {name} at {lat}, {lon}: {geocode_error}", exc_info=True)
                    return jsonify({
                        'success': False,
                        'error': f'Geocoding exception: {str(geocode_error)}',
                        'location': {}
                    }), 500
                
                # Check if geocoding returned any useful data
                has_location_data = location_info.get('city') or location_info.get('state') or location_info.get('country')
                
                if not has_location_data:
                    conn.close()
                    self.logger.warning(f"Geocoding returned no location data for {name} at {lat}, {lon}. Result: {location_info}")
                    return jsonify({
                        'success': False,
                        'error': 'Geocoding returned no location data. The coordinates may be invalid or the geocoding service may be unavailable.',
                        'location': location_info
                    }), 500
                
                # Update database with new location data
                cursor.execute('''
                    UPDATE complete_contact_tracking
                    SET city = ?, state = ?, country = ?
                    WHERE public_key = ?
                ''', (
                    location_info.get('city'),
                    location_info.get('state'),
                    location_info.get('country'),
                    public_key
                ))
                
                conn.commit()
                conn.close()
                
                # Build success message with what was found
                found_parts = []
                if location_info.get('city'):
                    found_parts.append(f"city: {location_info['city']}")
                if location_info.get('state'):
                    found_parts.append(f"state: {location_info['state']}")
                if location_info.get('country'):
                    found_parts.append(f"country: {location_info['country']}")
                
                success_message = f'Successfully geocoded {name} - Found {", ".join(found_parts)}'
                self.logger.info(f"Successfully geocoded {name}: {location_info}")
                
                return jsonify({
                    'success': True,
                    'location': location_info,
                    'message': success_message
                })
                
            except Exception as e:
                self.logger.error(f"Error geocoding contact: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500
    
    def _setup_socketio_handlers(self):
        """Setup SocketIO event handlers using modern patterns"""
        
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection"""
            client_id = request.sid
            self.logger.info(f"Client connected: {client_id}")
            
            # Check client limit
            if len(self.connected_clients) >= self.max_clients:
                self.logger.warning(f"Client limit reached ({self.max_clients}), rejecting connection")
                disconnect()
                return False
            
            # Track client
            self.connected_clients[client_id] = {
                'connected_at': time.time(),
                'last_activity': time.time(),
                'subscribed_commands': False,
                'subscribed_packets': False
            }
            
            # Connection status is shown via the green indicator in the navbar, no toast needed
            self.logger.info(f"Client {client_id} connected. Total clients: {len(self.connected_clients)}")
        
        @self.socketio.on('disconnect')
        def handle_disconnect(data=None):
            """Handle client disconnection"""
            client_id = request.sid
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]
                self.logger.info(f"Client {client_id} disconnected. Total clients: {len(self.connected_clients)}")
        
        @self.socketio.on('subscribe_commands')
        def handle_subscribe_commands():
            """Handle command stream subscription"""
            client_id = request.sid
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['subscribed_commands'] = True
                emit('status', {'message': 'Subscribed to command stream'})
                self.logger.debug(f"Client {client_id} subscribed to commands")
        
        @self.socketio.on('subscribe_packets')
        def handle_subscribe_packets():
            """Handle packet stream subscription"""
            client_id = request.sid
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['subscribed_packets'] = True
                emit('status', {'message': 'Subscribed to packet stream'})
                self.logger.debug(f"Client {client_id} subscribed to packets")
        
        @self.socketio.on('ping')
        def handle_ping():
            """Handle client ping (modern ping/pong pattern)"""
            client_id = request.sid
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['last_activity'] = time.time()
                emit('pong')  # Server responds with pong (Flask-SocketIO 5.x pattern)
        
        @self.socketio.on_error_default
        def default_error_handler(e):
            """Handle SocketIO errors gracefully"""
            self.logger.error(f"SocketIO error: {e}")
            emit('error', {'message': str(e)})
    
    def _handle_command_data(self, command_data):
        """Handle incoming command data from bot"""
        try:
            # Broadcast to subscribed clients
            subscribed_clients = [
                client_id for client_id, client_info in self.connected_clients.items()
                if client_info.get('subscribed_commands', False)
            ]
            
            if subscribed_clients:
                self.socketio.emit('command_data', command_data, room=None)
                self.logger.debug(f"Broadcasted command data to {len(subscribed_clients)} clients")
        except Exception as e:
            self.logger.error(f"Error handling command data: {e}")
    
    def _handle_packet_data(self, packet_data):
        """Handle incoming packet data from bot"""
        try:
            # Broadcast to subscribed clients
            subscribed_clients = [
                client_id for client_id, client_info in self.connected_clients.items()
                if client_info.get('subscribed_packets', False)
            ]
            
            if subscribed_clients:
                self.socketio.emit('packet_data', packet_data, room=None)
                self.logger.debug(f"Broadcasted packet data to {len(subscribed_clients)} clients")
        except Exception as e:
            self.logger.error(f"Error handling packet data: {e}")
    
    def _start_database_polling(self):
        """Start background thread to poll database for new data"""
        import threading
        
        def poll_database():
            last_timestamp = 0
            while True:
                try:
                    import time
                    import sqlite3
                    import json
                    
                    # Get database path
                    db_path = self.config.get('Database', 'path', fallback='bot_data.db')
                    
                    # Connect to database
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # Get new data since last poll
                    cursor.execute('''
                        SELECT timestamp, data, type FROM packet_stream 
                        WHERE timestamp > ? 
                        ORDER BY timestamp ASC
                    ''', (last_timestamp,))
                    
                    rows = cursor.fetchall()
                    conn.close()
                    
                    # Process new data
                    for timestamp, data_json, data_type in rows:
                        try:
                            data = json.loads(data_json)
                            
                            # Broadcast based on type
                            if data_type == 'command':
                                self._handle_command_data(data)
                            elif data_type == 'packet':
                                self._handle_packet_data(data)
                            elif data_type == 'routing':
                                self._handle_packet_data(data)  # Treat routing as packet data
                                
                        except Exception as e:
                            self.logger.debug(f"Error processing database data: {e}")
                    
                    # Update last timestamp
                    if rows:
                        last_timestamp = rows[-1][0]
                    
                    # Sleep before next poll
                    time.sleep(0.5)  # Poll every 500ms
                    
                except Exception as e:
                    self.logger.debug(f"Database polling error: {e}")
                    time.sleep(1)  # Wait longer on error
        
        # Start polling thread
        polling_thread = threading.Thread(target=poll_database, daemon=True)
        polling_thread.start()
        self.logger.info("Database polling started")
    
    def _start_cleanup_scheduler(self):
        """Start background thread for periodic database cleanup"""
        import threading
        
        def cleanup_scheduler():
            import time
            while True:
                try:
                    # Clean up old data every hour
                    time.sleep(3600)  # 1 hour
                    
                    # Clean up data older than 7 days
                    self._cleanup_old_data(days_to_keep=7)
                    
                except Exception as e:
                    self.logger.debug(f"Error in cleanup scheduler: {e}")
                    time.sleep(60)  # Sleep on error
        
        # Start the cleanup thread
        cleanup_thread = threading.Thread(target=cleanup_scheduler, daemon=True)
        cleanup_thread.start()
        self.logger.info("Cleanup scheduler started")
    
    def _cleanup_old_data(self, days_to_keep: int = 7):
        """Clean up old packet stream data to prevent database bloat"""
        try:
            import sqlite3
            import time
            
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            
            # Get database path
            db_path = self.config.get('Database', 'path', fallback='bot_data.db')
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Clean up old packet stream data
            cursor.execute('DELETE FROM packet_stream WHERE timestamp < ?', (cutoff_time,))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old packet stream entries (older than {days_to_keep} days)")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old packet stream data: {e}")
    
    def _get_database_stats(self):
        """Get comprehensive database statistics for dashboard"""
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get all available tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            stats = {
                'timestamp': time.time(),
                'connected_clients': len(self.connected_clients),
                'tables': tables
            }
            
            # Contact and tracking statistics
            if 'complete_contact_tracking' in tables:
                cursor.execute("SELECT COUNT(*) FROM complete_contact_tracking")
                stats['total_contacts'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM complete_contact_tracking 
                    WHERE last_heard > datetime('now', '-24 hours')
                """)
                stats['contacts_24h'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM complete_contact_tracking 
                    WHERE last_heard > datetime('now', '-7 days')
                """)
                stats['contacts_7d'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM complete_contact_tracking 
                    WHERE is_currently_tracked = 1
                """)
                stats['tracked_contacts'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT AVG(hop_count) FROM complete_contact_tracking 
                    WHERE hop_count IS NOT NULL
                """)
                avg_hops = cursor.fetchone()[0]
                stats['avg_hop_count'] = round(avg_hops, 1) if avg_hops else 0
                
                cursor.execute("""
                    SELECT MAX(hop_count) FROM complete_contact_tracking 
                    WHERE hop_count IS NOT NULL
                """)
                stats['max_hop_count'] = cursor.fetchone()[0] or 0
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT role) FROM complete_contact_tracking 
                    WHERE role IS NOT NULL
                """)
                stats['unique_roles'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT device_type) FROM complete_contact_tracking 
                    WHERE device_type IS NOT NULL
                """)
                stats['unique_device_types'] = cursor.fetchone()[0]
            
            # Advertisement statistics using daily tracking table
            if 'daily_stats' in tables:
                # Total advertisements (all time)
                cursor.execute("""
                    SELECT SUM(advert_count) FROM daily_stats
                """)
                total_adverts = cursor.fetchone()[0]
                stats['total_advertisements'] = total_adverts or 0
                
                # 24h advertisements
                cursor.execute("""
                    SELECT SUM(advert_count) FROM daily_stats 
                    WHERE date = date('now')
                """)
                stats['advertisements_24h'] = cursor.fetchone()[0] or 0
                
                # 7d advertisements (last 7 days, excluding today)
                cursor.execute("""
                    SELECT SUM(advert_count) FROM daily_stats 
                    WHERE date >= date('now', '-7 days') AND date < date('now')
                """)
                stats['advertisements_7d'] = cursor.fetchone()[0] or 0
                
                # Nodes per day statistics
                cursor.execute("""
                    SELECT COUNT(DISTINCT public_key) FROM daily_stats 
                    WHERE date = date('now')
                """)
                stats['nodes_24h'] = cursor.fetchone()[0] or 0
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT public_key) FROM daily_stats 
                    WHERE date >= date('now', '-6 days')
                """)
                stats['nodes_7d'] = cursor.fetchone()[0] or 0
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT public_key) FROM daily_stats
                """)
                stats['nodes_all'] = cursor.fetchone()[0] or 0
            else:
                # Fallback to old method if daily table doesn't exist yet
                if 'complete_contact_tracking' in tables:
                    cursor.execute("""
                        SELECT SUM(advert_count) FROM complete_contact_tracking
                    """)
                    total_adverts = cursor.fetchone()[0]
                    stats['total_advertisements'] = total_adverts or 0
                    
                    cursor.execute("""
                        SELECT SUM(advert_count) FROM complete_contact_tracking 
                        WHERE last_heard > datetime('now', '-24 hours')
                    """)
                    stats['advertisements_24h'] = cursor.fetchone()[0] or 0
                    
                    cursor.execute("""
                        SELECT SUM(advert_count) FROM complete_contact_tracking 
                        WHERE last_heard > datetime('now', '-7 days')
                    """)
                    stats['advertisements_7d'] = cursor.fetchone()[0] or 0
            
            # Repeater contacts (if exists)
            if 'repeater_contacts' in tables:
                cursor.execute("SELECT COUNT(*) FROM repeater_contacts")
                stats['repeater_contacts'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM repeater_contacts WHERE is_active = 1")
                stats['active_repeater_contacts'] = cursor.fetchone()[0]
            
            # Cache statistics
            cache_tables = [t for t in tables if 'cache' in t]
            stats['cache_tables'] = cache_tables
            stats['total_cache_entries'] = 0
            stats['active_cache_entries'] = 0
            
            for table in cache_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                stats['total_cache_entries'] += count
                stats[f'{table}_count'] = count
                
                # Get active entries (not expired)
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE expires_at > datetime('now')")
                active_count = cursor.fetchone()[0]
                stats['active_cache_entries'] += active_count
                stats[f'{table}_active'] = active_count
            
            # Message and command statistics (if stats tables exist)
            if 'message_stats' in tables:
                cursor.execute("SELECT COUNT(*) FROM message_stats")
                stats['total_messages'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM message_stats 
                    WHERE timestamp > strftime('%s', 'now', '-24 hours')
                """)
                stats['messages_24h'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT sender_id) FROM message_stats 
                    WHERE timestamp > strftime('%s', 'now', '-24 hours')
                """)
                stats['unique_senders_24h'] = cursor.fetchone()[0]
                
                # Total unique users and channels
                cursor.execute("SELECT COUNT(DISTINCT sender_id) FROM message_stats")
                stats['unique_users_total'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(DISTINCT channel) FROM message_stats WHERE channel IS NOT NULL")
                stats['unique_channels_total'] = cursor.fetchone()[0]
                
                # Top users (most frequent message senders)
                cursor.execute("""
                    SELECT sender_id, COUNT(*) as count 
                    FROM message_stats 
                    GROUP BY sender_id 
                    ORDER BY count DESC 
                    LIMIT 15
                """)
                stats['top_users'] = [{'user': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            if 'command_stats' in tables:
                cursor.execute("SELECT COUNT(*) FROM command_stats")
                stats['total_commands'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM command_stats 
                    WHERE timestamp > strftime('%s', 'now', '-24 hours')
                """)
                stats['commands_24h'] = cursor.fetchone()[0]
                
                # Top commands
                cursor.execute("""
                    SELECT command_name, COUNT(*) as count 
                    FROM command_stats 
                    GROUP BY command_name 
                    ORDER BY count DESC 
                    LIMIT 15
                """)
                stats['top_commands'] = [{'command': row[0], 'count': row[1]} for row in cursor.fetchall()]
                
                # Bot reply rate (commands that got responses)
                cursor.execute("""
                    SELECT COUNT(*) FROM command_stats WHERE response_sent = 1
                """)
                replied_commands = cursor.fetchone()[0]
                total_commands = stats.get('total_commands', 0)
                if total_commands > 0:
                    stats['bot_reply_rate'] = round((replied_commands / total_commands) * 100, 1)
                else:
                    stats['bot_reply_rate'] = 0
                
                # Top channels by message count
                cursor.execute("""
                    SELECT channel, COUNT(*) as message_count, COUNT(DISTINCT sender_id) as unique_users
                    FROM message_stats 
                    WHERE channel IS NOT NULL
                    GROUP BY channel 
                    ORDER BY message_count DESC 
                    LIMIT 10
                """)
                stats['top_channels'] = [
                    {'channel': row[0], 'messages': row[1], 'users': row[2]} 
                    for row in cursor.fetchall()
                ]
            
            # Path statistics (if path_stats table exists)
            if 'path_stats' in tables:
                cursor.execute("""
                    SELECT sender_id, path_length, path_string, timestamp
                    FROM path_stats 
                    ORDER BY path_length DESC 
                    LIMIT 1
                """)
                longest_path = cursor.fetchone()
                if longest_path:
                    stats['longest_path'] = {
                        'user': longest_path[0],
                        'path_length': longest_path[1],
                        'path_string': longest_path[2],
                        'timestamp': longest_path[3]
                    }
                
                # Top paths (longest paths)
                cursor.execute("""
                    SELECT sender_id, path_length, path_string, timestamp
                    FROM path_stats 
                    ORDER BY path_length DESC 
                    LIMIT 5
                """)
                stats['top_paths'] = [
                    {
                        'user': row[0], 
                        'path_length': row[1], 
                        'path_string': row[2], 
                        'timestamp': row[3]
                    } 
                    for row in cursor.fetchall()
                ]
            
            # Network health metrics
            if 'complete_contact_tracking' in tables:
                cursor.execute("""
                    SELECT AVG(snr) FROM complete_contact_tracking 
                    WHERE snr IS NOT NULL AND last_heard > datetime('now', '-24 hours')
                """)
                avg_snr = cursor.fetchone()[0]
                stats['avg_snr_24h'] = round(avg_snr, 1) if avg_snr else 0
                
                cursor.execute("""
                    SELECT AVG(signal_strength) FROM complete_contact_tracking 
                    WHERE signal_strength IS NOT NULL AND last_heard > datetime('now', '-24 hours')
                """)
                avg_signal = cursor.fetchone()[0]
                stats['avg_signal_strength_24h'] = round(avg_signal, 1) if avg_signal else 0
            
            # Geographic distribution
            if 'complete_contact_tracking' in tables:
                cursor.execute("""
                    SELECT COUNT(DISTINCT country) FROM complete_contact_tracking 
                    WHERE country IS NOT NULL AND country != ''
                """)
                stats['countries'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT state) FROM complete_contact_tracking 
                    WHERE state IS NOT NULL AND state != ''
                """)
                stats['states'] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT city) FROM complete_contact_tracking 
                    WHERE city IS NOT NULL AND city != ''
                """)
                stats['cities'] = cursor.fetchone()[0]
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting database stats: {e}")
            return {'error': str(e)}
        finally:
            if conn:
                conn.close()
    
    def _get_database_info(self):
        """Get comprehensive database information for database page"""
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            table_names = [row[0] for row in cursor.fetchall()]
            
            # Get table information
            tables = []
            total_records = 0
            
            for table_name in table_names:
                try:
                    # Get record count
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    record_count = cursor.fetchone()[0]
                    total_records += record_count
                    
                    # Get table size (approximate)
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = cursor.fetchall()
                    
                    # Estimate size (rough calculation)
                    estimated_size = record_count * len(columns) * 50  # Rough estimate
                    size_str = f"{estimated_size:,} bytes" if estimated_size < 1024 else f"{estimated_size/1024:.1f} KB"
                    
                    # Get table description based on name
                    description = self._get_table_description(table_name)
                    
                    tables.append({
                        'name': table_name,
                        'record_count': record_count,
                        'size': size_str,
                        'description': description
                    })
                    
                except Exception as e:
                    self.logger.debug(f"Error getting info for table {table_name}: {e}")
                    tables.append({
                        'name': table_name,
                        'record_count': 0,
                        'size': 'Unknown',
                        'description': 'Error reading table'
                    })
            
            # Get database file size
            import os
            db_path = self.config.get('Database', 'path', fallback='bot_data.db')
            try:
                db_size_bytes = os.path.getsize(db_path)
                if db_size_bytes < 1024:
                    db_size = f"{db_size_bytes} bytes"
                elif db_size_bytes < 1024 * 1024:
                    db_size = f"{db_size_bytes/1024:.1f} KB"
                else:
                    db_size = f"{db_size_bytes/(1024*1024):.1f} MB"
            except:
                db_size = "Unknown"
            
            return {
                'total_tables': len(table_names),
                'total_records': total_records,
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                'db_size': db_size,
                'tables': tables
            }
            
        except Exception as e:
            self.logger.error(f"Error getting database info: {e}")
            return {
                'total_tables': 0,
                'total_records': 0,
                'last_updated': 'Error',
                'db_size': 'Unknown',
                'tables': []
            }
        finally:
            if conn:
                conn.close()
    
    def _get_table_description(self, table_name):
        """Get human-readable description for table"""
        descriptions = {
            'packet_stream': 'Real-time packet and command data stream',
            'complete_contact_tracking': 'Contact tracking and device information',
            'repeater_contacts': 'Repeater contact management',
            'message_stats': 'Message statistics and analytics',
            'command_stats': 'Command execution statistics',
            'path_stats': 'Network path statistics',
            'geocoding_cache': 'Geocoding service cache',
            'generic_cache': 'General purpose cache storage'
        }
        return descriptions.get(table_name, 'Database table')
    
    def _optimize_database(self):
        """Optimize database using VACUUM, ANALYZE, and REINDEX"""
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get initial database size
            import os
            db_path = self.config.get('Database', 'path', fallback='bot_data.db')
            initial_size = os.path.getsize(db_path)
            
            # Perform VACUUM to reclaim unused space
            self.logger.info("Starting database VACUUM...")
            cursor.execute("VACUUM")
            vacuum_size = os.path.getsize(db_path)
            vacuum_saved = initial_size - vacuum_size
            
            # Perform ANALYZE to update table statistics
            self.logger.info("Starting database ANALYZE...")
            cursor.execute("ANALYZE")
            
            # Get all tables for REINDEX
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Perform REINDEX on all tables
            self.logger.info("Starting database REINDEX...")
            reindexed_tables = []
            for table in tables:
                if table != 'sqlite_sequence':  # Skip system tables
                    try:
                        cursor.execute(f"REINDEX {table}")
                        reindexed_tables.append(table)
                    except Exception as e:
                        self.logger.debug(f"Could not reindex table {table}: {e}")
            
            # Get final database size
            final_size = os.path.getsize(db_path)
            total_saved = initial_size - final_size
            
            # Format size information
            def format_size(size_bytes):
                if size_bytes < 1024:
                    return f"{size_bytes} bytes"
                elif size_bytes < 1024 * 1024:
                    return f"{size_bytes/1024:.1f} KB"
                else:
                    return f"{size_bytes/(1024*1024):.1f} MB"
            
            return {
                'success': True,
                'vacuum_result': f"VACUUM completed - saved {format_size(vacuum_saved)}",
                'analyze_result': f"ANALYZE completed - updated statistics for {len(tables)} tables",
                'reindex_result': f"REINDEX completed - rebuilt indexes for {len(reindexed_tables)} tables",
                'initial_size': format_size(initial_size),
                'final_size': format_size(final_size),
                'total_saved': format_size(total_saved),
                'tables_processed': len(tables),
                'tables_reindexed': len(reindexed_tables)
            }
            
        except Exception as e:
            self.logger.error(f"Error optimizing database: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            if conn:
                conn.close()
    
    def _get_tracking_data(self):
        """Get contact tracking data"""
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get bot location from config
            bot_lat = self.config.getfloat('Bot', 'bot_latitude', fallback=None)
            bot_lon = self.config.getfloat('Bot', 'bot_longitude', fallback=None)
            
            cursor.execute("""
                SELECT public_key, name, role, device_type, 
                       latitude, longitude, city, state, country,
                       snr, hop_count, first_heard, last_heard,
                       advert_count, is_currently_tracked,
                       raw_advert_data, signal_strength,
                       COUNT(*) as total_messages,
                       MAX(last_advert_timestamp) as last_message
                FROM complete_contact_tracking 
                GROUP BY public_key, name, role, device_type, 
                         latitude, longitude, city, state, country,
                         snr, hop_count, first_heard, last_heard,
                         advert_count, is_currently_tracked,
                         raw_advert_data, signal_strength
                ORDER BY last_heard DESC
            """)
            
            tracking = []
            for row in cursor.fetchall():
                # Parse raw advertisement data if available
                raw_advert_data_parsed = None
                if row['raw_advert_data']:
                    try:
                        import json
                        raw_advert_data_parsed = json.loads(row['raw_advert_data'])
                    except:
                        raw_advert_data_parsed = None
                
                # Calculate distance if both bot and contact have coordinates
                distance = None
                if (bot_lat is not None and bot_lon is not None and 
                    row['latitude'] is not None and row['longitude'] is not None):
                    distance = self._calculate_distance(bot_lat, bot_lon, row['latitude'], row['longitude'])
                
                tracking.append({
                    'user_id': row['public_key'],
                    'username': row['name'],
                    'role': row['role'],
                    'device_type': row['device_type'],
                    'latitude': row['latitude'],
                    'longitude': row['longitude'],
                    'city': row['city'],
                    'state': row['state'],
                    'country': row['country'],
                    'snr': row['snr'],
                    'hop_count': row['hop_count'],
                    'first_heard': row['first_heard'],
                    'last_seen': row['last_heard'],
                    'advert_count': row['advert_count'],
                    'is_currently_tracked': row['is_currently_tracked'],
                    'raw_advert_data': row['raw_advert_data'],
                    'raw_advert_data_parsed': raw_advert_data_parsed,
                    'signal_strength': row['signal_strength'],
                    'total_messages': row['total_messages'],
                    'last_message': row['last_message'],
                    'distance': distance
                })
            
            # Get server statistics for daily tracking using direct database queries
            server_stats = {}
            try:
                # Check if daily_stats table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_stats'")
                if cursor.fetchone():
                    # 24h: Last 24 hours of advertisements
                    cursor.execute("""
                        SELECT SUM(advert_count) FROM daily_stats 
                        WHERE date >= date('now', '-1 day')
                    """)
                    server_stats['advertisements_24h'] = cursor.fetchone()[0] or 0
                    
                    # 7d: Previous 6 days (excluding today)
                    cursor.execute("""
                        SELECT SUM(advert_count) FROM daily_stats 
                        WHERE date >= date('now', '-7 days') AND date < date('now')
                    """)
                    server_stats['advertisements_7d'] = cursor.fetchone()[0] or 0
                    
                    # All: Everything
                    cursor.execute("""
                        SELECT SUM(advert_count) FROM daily_stats
                    """)
                    server_stats['total_advertisements'] = cursor.fetchone()[0] or 0
                    
                    # Nodes per day statistics
                    cursor.execute("""
                        SELECT COUNT(DISTINCT public_key) FROM daily_stats 
                        WHERE date = date('now')
                    """)
                    server_stats['nodes_24h'] = cursor.fetchone()[0] or 0
                    
                    cursor.execute("""
                        SELECT COUNT(DISTINCT public_key) FROM daily_stats 
                        WHERE date >= date('now', '-7 days') AND date < date('now')
                    """)
                    server_stats['nodes_7d'] = cursor.fetchone()[0] or 0
                    
                    cursor.execute("""
                        SELECT COUNT(DISTINCT public_key) FROM daily_stats
                    """)
                    server_stats['nodes_all'] = cursor.fetchone()[0] or 0
                    
            except Exception as e:
                self.logger.debug(f"Could not get server stats: {e}")
            
            return {
                'tracking_data': tracking,
                'server_stats': server_stats
            }
        except Exception as e:
            self.logger.error(f"Error getting tracking data: {e}")
            return {'error': str(e)}
        finally:
            if conn:
                conn.close()
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points using Haversine formula"""
        import math
        
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of earth in kilometers
        r = 6371
        
        return c * r
    
    def _get_cache_data(self):
        """Get cache data"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get cache statistics
            cursor.execute("SELECT COUNT(*) FROM adverts")
            total_adverts = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) FROM adverts 
                WHERE timestamp > datetime('now', '-1 hour')
            """)
            recent_adverts = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) FROM adverts 
                WHERE timestamp > datetime('now', '-24 hours')
            """)
            active_users = cursor.fetchone()[0]
            
            return {
                'total_adverts': total_adverts,
                'recent_adverts_1h': recent_adverts,
                'active_users_24h': active_users,
                'timestamp': time.time()
            }
        except Exception as e:
            self.logger.error(f"Error getting cache data: {e}")
            return {'error': str(e)}
    
    
    def _get_bot_uptime(self):
        """Get bot uptime in seconds from database"""
        try:
            # Get start time from database metadata
            start_time = self.db_manager.get_bot_start_time()
            if start_time:
                return int(time.time() - start_time)
            else:
                # Fallback: try to get earliest message timestamp
                conn = self._get_db_connection()
                cursor = conn.cursor()
                
                # Try to get earliest message timestamp as fallback
                cursor.execute("""
                    SELECT MIN(timestamp) FROM message_stats 
                    WHERE timestamp IS NOT NULL
                """)
                result = cursor.fetchone()
                if result and result[0]:
                    return int(time.time() - result[0])
                
                return 0
        except Exception as e:
            self.logger.debug(f"Could not get bot start time from database: {e}")
            return 0
    
    def run(self, host='127.0.0.1', port=8080, debug=False):
        """Run the modern web viewer"""
        self.logger.info(f"Starting modern web viewer on {host}:{port}")
        try:
            self.socketio.run(
                self.app,
                host=host,
                port=port,
                debug=debug,
                allow_unsafe_werkzeug=True
            )
        except Exception as e:
            self.logger.error(f"Error running web viewer: {e}")
            raise

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='MeshCore Bot Data Viewer')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    viewer = BotDataViewer()
    viewer.run(host=args.host, port=args.port, debug=args.debug)
