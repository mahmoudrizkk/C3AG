# Pico2W/main2.py
# Application for HX711 Load Cell with Keypad and OLED UI
# Fixed version with proper keypad debouncing

import time
import ujson
import machine
import network
import requests
import socket
import os
from ssd1306 import SSD1306_I2C
from hx711 import WeightSensor, save_calibration, load_calibration, calibrate_with_known_weight

# --- HARDWARE CONFIGURATION ---
# HX711 Load Cell Pins (Change if needed)
HX711_CLK_PIN = 14
HX711_DAT_PIN = 15

# Wifi Creds
WIFI_SSID = "UE-DT"
WIFI_PASSWORD = "UE-DT@2023"
API_ENDPOINT = "http://corn.runasp.net/api/ChickenWeighing"

# --- APPLICATION SETTINGS ---
STABILITY_THRESHOLD_G = 200  # (grams) How much the weight can fluctuate to be considered stable
STABILITY_DURATION_S = 0.5   # (seconds) How long the weight must be stable before saving
ZERO_THRESHOLD_G = 100      # (grams) Weights below this are considered zero and reset the stability timer

SAVED = False

# --- KEYPAD DEBOUNCING GLOBALS ---
last_key_time = 0
last_key_pressed = None
DEBOUNCE_TIME_MS = 150  # Debounce time in milliseconds

# --- HARDWARE INITIALIZATION ---
# I2C and OLED Display
i2c = machine.I2C(1, scl=machine.Pin(3), sda=machine.Pin(2), freq=400000)
oled = SSD1306_I2C(128, 64, i2c)

# Keypad 4x4 Setup
COL_PINS = [6, 7, 8, 9]
ROW_PINS = [10, 11, 12, 13]
KEYS = [
    ['1', '4', '7', 'M'],
    ['2', '5', '8', '0'],
    ['3', '6', '9', 'C'],
    ['F1', 'F2', 'F3', 'E']
]
rows = [machine.Pin(pin, machine.Pin.OUT) for pin in ROW_PINS]
cols = [machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_UP) for pin in COL_PINS]

# HX711 Weight Sensor
sensor = WeightSensor(HX711_CLK_PIN, HX711_DAT_PIN)

# --- OTA UPDATER CLASS ---
class OTAUpdater:
    def __init__(self, ssid, password, github_repo, github_src_dir='', main_dir='main', new_version_dir='next'):
        self.ssid = ssid
        self.password = password
        self.github_repo = github_repo.rstrip('/').replace('https://github.com/', '')
        self.github_src_dir = '' if len(github_src_dir) < 1 else github_src_dir.rstrip('/') + '/'
        self.main_dir = main_dir
        self.new_version_dir = new_version_dir
        
        # version endpoint
        self.version_url = 'https://raw.githubusercontent.com/{}/main/version.json'.format(self.github_repo)
        self.firmware_url = 'https://raw.githubusercontent.com/{}/main/'.format(self.github_repo)
        
        # internal
        self.version_file = 'version.json'
        self.version_file_new = self.new_version_dir + '/version.json'
    
    def check_for_update_to_install_during_next_reboot(self):
        """Check if update was downloaded, ota install, and perform reboot if required"""
        if self.new_version_dir in os.listdir():
            if '.version' in os.listdir(self.new_version_dir):
                latest_version = self.get_version(self.new_version_dir + '/.version')
                current_version = self.get_version(self.version_file)
                if latest_version > current_version:
                    self.install_update_if_available()
                    return True
        return False
    
    def download_and_install_update_if_available(self):
        """Check for updates and install if available"""
        current_version = self.get_version(self.version_file)
        latest_version = self.download_latest_version()
        
        if latest_version > current_version:
            self.install_update_if_available()
            return True
        return False
    
    def check_for_update(self):
        """Check if update is available"""
        current_version = self.get_version(self.version_file)
        latest_version = self.get_latest_version()
        return latest_version > current_version
    
    def download_latest_version(self):
        """Download the latest version"""
        latest_version = self.get_latest_version()
        self.download_all_files(latest_version)
        return latest_version
    
    def get_latest_version(self):
        """Get the latest version from GitHub"""
        response = requests.get(self.version_url)
        return response.json()['version']
    
    def get_version(self, version_file):
        """Get version from file"""
        try:
            with open(version_file, 'r') as f:
                version_json = ujson.loads(f.read())
                return version_json['version']
        except:
            return '0.0.0'
    
    def download_all_files(self, version):
        """Download all files from GitHub"""
        file_list = self.get_file_list()
        for file in file_list:
            self.download_file(file)
        self.create_version_file(version)
    
    def get_file_list(self):
        """Get list of files from GitHub"""
        response = requests.get(self.firmware_url + 'file_list.json')
        return response.json()
    
    def download_file(self, file):
        """Download a file from GitHub"""
        print('Downloading: ' + file)
        response = requests.get(self.firmware_url + self.github_src_dir + file)
        if response.status_code == 200:
            os.makedirs(self.new_version_dir + '/' + os.path.dirname(file), exist_ok=True)
            with open(self.new_version_dir + '/' + file, 'w') as f:
                f.write(response.text)
        else:
            print('Error downloading: ' + file)
    
    def create_version_file(self, version):
        """Create version file"""
        version_json = {'version': version}
        os.makedirs(self.new_version_dir, exist_ok=True)
        with open(self.new_version_dir + '/.version', 'w') as f:
            f.write(ujson.dumps(version_json))
    
    def install_update_if_available(self):
        """Install the update"""
        if self.new_version_dir in os.listdir():
            if '.version' in os.listdir(self.new_version_dir):
                latest_version = self.get_version(self.new_version_dir + '/.version')
                current_version = self.get_version(self.version_file)
                if latest_version > current_version:
                    self.rmtree(self.main_dir)
                    os.rename(self.new_version_dir, self.main_dir)
                    machine.reset()
    
    def rmtree(self, directory):
        """Remove directory and all contents"""
        for entry in os.ilistdir(directory):
            is_dir = entry[1] == 0x4000
            if is_dir:
                self.rmtree(directory + '/' + entry[0])
            else:
                os.remove(directory + '/' + entry[0])
        os.rmdir(directory)

# --- UI HELPER FUNCTIONS ---
def display_message(line1, line2="", line3="", line4="", duration_ms=0):
    oled.fill(0)
    oled.text(line1, 0, 5)
    oled.text(line2, 0, 20)
    oled.text(line3, 0, 35)
    oled.text(line4, 0, 50)
    oled.show()
    if duration_ms > 0:
        time.sleep_ms(duration_ms)

# --- IMPROVED KEYPAD FUNCTIONS ---
def scan_keypad_debounced():
    """Improved keypad scanning with proper debouncing"""
    global last_key_time, last_key_pressed
    
    current_time = time.ticks_ms()
    
    # Check if enough time has passed since last key press
    if time.ticks_diff(current_time, last_key_time) < DEBOUNCE_TIME_MS:
        return None
    
    # Scan for pressed keys
    pressed_key = None
    for r_idx, row in enumerate(rows):
        for r in rows: 
            r.value(1)
        row.value(0)
        
        for c_idx, col in enumerate(cols):
            if col.value() == 0:
                pressed_key = KEYS[c_idx][r_idx]
                break
        
        if pressed_key:
            break
    
    # Reset all rows
    for r in rows:
        r.value(1)
    
    # If no key is pressed, reset last_key_pressed
    if pressed_key is None:
        last_key_pressed = None
        return None
    
    # If same key is still being held, ignore
    if pressed_key == last_key_pressed:
        return None
    
    # New key press detected
    last_key_pressed = pressed_key
    last_key_time = current_time
    return pressed_key

def wait_for_key_release():
    """Wait until all keys are released - useful for critical operations"""
    while True:
        any_pressed = False
        for r_idx, row in enumerate(rows):
            for r in rows: 
                r.value(1)
            row.value(0)
            
            for col in cols:
                if col.value() == 0:
                    any_pressed = True
                    break
            
            if any_pressed:
                break
        
        if not any_pressed:
            break
        
        time.sleep_ms(10)
    
    # Reset all rows
    for r in rows:
        r.value(1)

def get_numeric_input(prompt):
    """Improved numeric input with better debouncing"""
    display_message(prompt, "Use keypad.", "Press 'E' to End.", "Press 'C' to Clear.")
    input_str = ""
    
    wait_for_key_release()  # Ensure no keys are pressed when starting
    
    while True:
        key = scan_keypad_debounced()
        
        if key and key in "0123456789":
            input_str += key
            display_message(prompt, input_str, "Press 'E' to End.", "Press 'C' to Clear.")
            
        elif key == 'C':
            input_str = ""
            display_message(prompt, input_str, "Press 'E' to End.", "Press 'C' to Clear.")
            
        elif key == 'E' and input_str:
            wait_for_key_release()  # Ensure key is released before returning
            return float(input_str)
        
        time.sleep_ms(10)  # Small delay to prevent busy waiting

def get_current_version():
    """Get current version for display"""
    try:
        with open("version.json", 'r') as f:
            version_json = ujson.loads(f.read())
            return str(version_json['version'])
    except:
        return "0"

def trigger_ota_update():
    """Handle OTA update process with password protection"""
    time.sleep(0.5)
    display_message("Enter Password:", "*", "Press 'E' to confirm", "Press 'C' to cancel")
    
    password_buffer = ""
    last_key = None
    
    while True:
        key = scan_keypad_debounced()
        
        if key and key != last_key:
            if key == 'E':  # Enter key
                if password_buffer == "1234":  # OTA password
                    display_message("Starting OTA...", "Please wait", "", "", 0)
                    try:
                        firmware_url = "https://github.com/mahmoudrizkk/C3AG/"
                        ota_updater = OTAUpdater(WIFI_SSID, WIFI_PASSWORD, firmware_url, "main.py")
                        ota_updater.download_and_install_update_if_available()
                        display_message("OTA Success", "Update completed", "", "", 3000)
                    except Exception as e:
                        display_message("OTA Failed", str(e)[:20], "", "", 3000)
                    return
                else:
                    display_message("Wrong Password!", "Try again", "", "", 2000)
                    password_buffer = ""
                    display_message("Enter Password:", "*", "Press 'E' to confirm", "Press 'C' to cancel")
            elif key == 'C':  # Cancel key
                display_message("Update Cancelled", "Returning to", "main menu", "", 2000)
                return
            elif key in '0123456789':  # Password digits
                password_buffer += key
                display_message("Enter Password:", "*" * min(len(password_buffer), 16), "Press 'E' to confirm", "Press 'C' to cancel")
            last_key = key
        elif not key:
            last_key = None
        
        time.sleep_ms(100)

# --- DATA HANDLING ---
def save_weight_data(weight_kg):
    try:
        with open("data.json", "r") as f:
            data = ujson.load(f)
    except (OSError, ValueError):
        data = []
    
    t = time.localtime()
    ftime = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5])
    
    entry = {"weight": round(weight_kg, 3), "date": ftime}
    data.append(entry)
    
    with open("data.json", "w") as f:
        ujson.dump(data, f)
    
    display_message("SAVED!", f"{weight_kg:.3f} kg", "", f"Total: {len(data)}", 2000)

def view_stored_data():
    try:
        with open("data.json", "r") as f:
            data = ujson.load(f)
    except (OSError, ValueError):
        display_message("No Data Found", "File not found", "or corrupted.", "", 2000)
        return
    
    if not data:
        display_message("No Readings", "Data file empty.", "", "", 2000)
        return
    
    # Show total count first
    display_message("Data Viewer", f"Total: {len(data)}", "Press 'E' to scroll", "Press 'C' to exit", 2000)
    
    wait_for_key_release()  # Ensure clean start
    
    # Browse through readings
    index = 0
    while index < len(data):
        entry = data[index]
        weight_kg = entry["weight"]
        date_str = entry["date"]
        
        # Format date for display (show only date and time, not full timestamp)
        try:
            date_parts = date_str.split('T')
            date_only = date_parts[0][5:]  # Remove year, show MM-DD
            time_only = date_parts[1][:5]  # Show HH:MM only
        except:
            date_only = date_str[:10]
            time_only = date_str[11:16]
        
        oled.fill(0)
        oled.text(f"Reading {index + 1}/{len(data)}", 0, 5)
        oled.text(f"Weight: {weight_kg:.3f}kg", 0, 20)
        oled.text(f"Date: {date_only}", 0, 35)
        oled.text(f"Time: {time_only}", 0, 50)
        oled.show()
        
        # Wait for user input with improved debouncing
        while True:
            key = scan_keypad_debounced()
            if key == 'E':  # Next reading
                index += 1
                break
            elif key == 'C':  # Exit viewer
                wait_for_key_release()
                return
            elif key == '0' and index > 0:  # Previous reading (use '0' key)
                index -= 1
                break
            time.sleep_ms(10)
    
    # End of data
    display_message("End of Data", f"Total: {len(data)}", "Press any key", "to return", 0)
    
    # Wait for any key to return
    while True:
        key = scan_keypad_debounced()
        if key:
            wait_for_key_release()
            break
        time.sleep_ms(10)

def delete_all_data():
    """Improved delete with better key handling"""
    display_message("DELETE ALL DATA?", "", "Press 'E' to confirm", "Press 'C' to cancel")
    
    wait_for_key_release()  # Make sure no keys are pressed when starting
    
    while True:
        key = scan_keypad_debounced()
        
        if key == 'E':
            wait_for_key_release()  # Wait for release before proceeding
            try:
                import os
                os.remove("data.json")
                display_message("DATA DELETED!", "All readings", "have been removed.", "", 2000)
            except OSError:
                display_message("Delete Failed", "File may not exist", "or is protected.", "", 2000)
            return
            
        elif key == 'C':
            wait_for_key_release()
            display_message("Cancelled", "Data preserved.", "", "", 1500)
            return
        
        time.sleep_ms(10)

def serve_request():
    # Show startup message
    oled.fill(0)
    oled.text("Starting Server...", 0, 0)
    oled.show()
    
    # Wi-Fi Access Point
    ap = network.WLAN(network.AP_IF)
    ap.config(essid="PicoServer", password="12345678")
    ap.active(True)

    # Wait for connection
    start_time = time.time()
    while not ap.active() and (time.time() - start_time < 10):  # 10s timeout
        time.sleep_ms(100)
    
    if not ap.active():
        display_message("AP Failed", "Could not start", "Wi-Fi AP", "", 2000)
        return

    # Display AP info
    oled.fill(0)
    oled.text("AP: PicoServer", 0, 0)
    oled.text("IP: " + ap.ifconfig()[0], 0, 10)
    oled.text("Pass: 12345678", 0, 20)
    oled.text("C:Cancel Server", 0, 30)
    oled.show()

    # Start web server
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.settimeout(0.5)  # Timeout for socket operations
    s.bind(addr)
    s.listen(1)

    last_client_time = time.time()
    wait_for_key_release()  # Ensure clean start
    
    while True:
        # Handle keypad input with improved debouncing
        key = scan_keypad_debounced()
        if key == 'M':  # Mode Switch
            wait_for_key_release()
            display_message("Switching to", "API Mode...")
            with open('mode.conf', 'w') as f:
                f.write('api')
            machine.reset()
        elif key == 'C':  # Cancel server
            wait_for_key_release()
            s.close()
            ap.active(False)
            display_message("Server Stopped", "Returning to", "main mode...", "", 1500)
            return

        # Handle client connections
        try:
            cl, addr = s.accept()
            last_client_time = time.time()
            
            try:
                request = cl.recv(1024).decode('utf-8')
                print("Request:", request)
                
                if "GET /data.json" in request:
                    try:
                        with open("data.json", "r") as f:
                            body = f.read()
                        response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n" + body
                    except Exception as e:
                        response = "HTTP/1.1 500 Internal Error\r\n\r\nError reading data"
                else:
                    response = "HTTP/1.1 404 Not Found\r\n\r\nResource not found"
                
                cl.send(response.encode('utf-8'))
            except Exception as e:
                print("Request handling error:", e)
                cl.send("HTTP/1.1 500 Server Error\r\n\r\n")
            finally:
                cl.close()
                
            # Briefly show client info
            oled.fill(0)
            oled.text("Client served", 0, 0)
            oled.text(addr[0], 0, 10)
            oled.show()
            time.sleep_ms(500)  # Show for 0.5s

        except OSError as e:
            if str(e) != 'timed out':  # Ignore timeout errors
                print("Socket error:", e)
        except Exception as e:
            print("Unexpected error:", e)
            
        # Update display periodically
        if time.time() - last_client_time > 5:  # Revert to AP info after 5s
            oled.fill(0)
            oled.text("AP: PicoServer", 0, 0)
            oled.text("IP: " + ap.ifconfig()[0], 0, 10)
            oled.text("Pass: 12345678", 0, 20)
            oled.text("C:Cancel Server", 0, 30)
            oled.show()

def connect_wifi():
    """Connect to WiFi with global credentials"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        display_message("Connecting to WiFi...", WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # Wait for connection with timeout
        for _ in range(20):  # ~10 second timeout
            if wlan.isconnected():
                break
            time.sleep(0.5)
    
    if wlan.isconnected():
        display_message("WiFi Connected!", wlan.ifconfig()[0], "", "", 1500)
        return True
    else:
        display_message("WiFi Failed!", "Check credentials", "", "", 2000)
        return False

def send_data_to_api():
    """Send data to API endpoint with proper error handling"""
    try:
        # First check if we have any data to send
        try:
            with open("data.json", "r") as f:
                data = f.read().strip()
                if not data or data == "[]":
                    display_message("No data to send", "", "", "", 1500)
                    return True
        except OSError:
            display_message("No data file", "found to send", "", "", 1500)
            return True
            
        # Connect to WiFi
        if not connect_wifi():
            return False
            
        # Send data
        display_message("Sending data...", "Please wait", "", "", 0)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(API_ENDPOINT, data=data, headers=headers)
        
        # Handle response
        if 200 <= response.status_code < 300:
            display_message("Data sent!", "Clearing local", "data file", "", 2000)
            with open("data.json", "w") as f:
                f.write("[]")  # Clear the file
            return True
        else:
            display_message("API Error:", f"Code: {response.status_code}", "Data not cleared", "", 3000)
            return False
            
    except Exception as e:
        display_message("Send Failed:", str(e)[:20], "", "", 3000)
        return False

# --- CORE FUNCTIONS ---
def tare_scale():
    display_message("Taring scale...", "Please wait.")
    # Get the current raw value as the new zero offset
    tare_value = sensor.hx.get_value_timeout(250000)
    if tare_value is not None:
        sensor.sample = tare_value
        # Save the new offset with the existing scaling factor
        save_calibration(sensor.sample, sensor.val)
        display_message("Tare Complete!", "", "", "", 1500)
    else:
        display_message("Tare Failed!", "No reading.", "Check sensor.", "", 2000)

def run_calibration():
    known_weight = get_numeric_input("Enter known weight (g):")
    
    display_message("Step 1: Tare", "Remove all weight", "Then press 'E'")
    wait_for_key_release()  # Ensure clean start
    
    # Wait for E key with proper debouncing
    while True:
        key = scan_keypad_debounced()
        if key == 'E':
            wait_for_key_release()
            break
        time.sleep_ms(10)
    
    # Getting the tare value
    tare_values = []
    display_message("Reading Tare...", "Please wait.")
    for _ in range(100):
        val = sensor.hx.get_value_timeout(250000)
        if val is not None: 
            tare_values.append(val)
    if not tare_values: 
        display_message("Error: No reading", "Check wiring.", "", "", 3000)
        return
    tare_value = sum(tare_values) / len(tare_values)

    display_message("Step 2: Weigh", f"Place {known_weight}g", "Then press 'E'")
    
    # Wait for E key with proper debouncing
    while True:
        key = scan_keypad_debounced()
        if key == 'E':
            wait_for_key_release()
            break
        time.sleep_ms(10)

    # Getting the value with weight
    weight_values = []
    display_message("Reading Weight...", "Please wait.")
    for _ in range(100):
        val = sensor.hx.get_value_timeout(250000)
        if val is not None: 
            weight_values.append(val)
    if not weight_values: 
        display_message("Error: No reading", "Check wiring.", "", "", 3000)
        return
    weight_value = sum(weight_values) / len(weight_values)
    
    # Calculate and save
    diff = weight_value - tare_value
    if abs(diff) < 1:
        display_message("Error: No change", "Check weight/wiring.", "", "", 3000)
        return

    scaling_factor = -diff / known_weight
    sensor.sample = tare_value
    sensor.val = scaling_factor
    save_calibration(sensor.sample, sensor.val)
    
    display_message("Calibration Done!", f"Factor: {scaling_factor:.2f}", "", "", 2000)

# --- MAIN APPLICATION ---
def main():
    global SAVED  # Access the global flag
    
    # Get current version
    current_version = get_current_version()
    
    # Show startup with version
    display_message("Starting...", "Weight System", f"Version: {current_version}", "", 2000)
    sensor.setup()

    # Load calibration or force user to calibrate
    calibration_data = load_calibration()
    if calibration_data:
        sensor.sample, sensor.val = calibration_data
    else:
        display_message("Calibration needed!")
        run_calibration()

    last_stable_time = None
    recent_weights = []
    SAVED = False  # Initialize the save-state flag

    display_message("Ready!", "", "C:Tare M:Calib", "F1:View F2:Send F3:Server 0:OTA", 1500)
    
    wait_for_key_release()  # Ensure clean start

    while True:
        # --- Handle Keypad Input with Improved Debouncing ---
        key = scan_keypad_debounced()
        if key == 'C':
            wait_for_key_release()
            tare_scale()
            SAVED = False  # Reset on tare
        elif key == 'M':
            wait_for_key_release()
            run_calibration()
            SAVED = False  # Reset on calibration
        elif key == 'F1':
            wait_for_key_release()
            view_stored_data()
            display_message("Ready!", "", "C:Tare M:Calib", "F1:View F2:Send F3:Server 0:OTA", 1500)
        elif key == 'F2':
            wait_for_key_release()
            if send_data_to_api():
                delete_all_data()
            display_message("Ready!", "", "C:Tare M:Calib", "F1:View F2:Send F3:Server 0:OTA", 1500)
        elif key == 'F3':
            wait_for_key_release()
            serve_request()
            display_message("Ready!", "", "C:Tare M:Calib", "F1:View F2:Send F3:Server 0:OTA", 1500)
        elif key == '0':  # Use '0' key for OTA update
            wait_for_key_release()
            trigger_ota_update()
            display_message("Ready!", "", "C:Tare M:Calib", "F1:View F2:Send F3:Server 0:OTA", 1500)
        
        # --- Read and Process Weight ---
        weight = sensor.get_stable_weight(samples=2, delay=0.01)

        if weight is not None:
            # Display current weight
            oled.fill(0)
            oled.text("Weight:", 0, 5)
            oled.text(f"{weight:.2f} kg", 10, 25)
            
            # Check if weight is below zero threshold (effectively zero)
            if weight <= (ZERO_THRESHOLD_G / 1000.0):
                SAVED = False  # Reset the saved flag when back to zero
                recent_weights = []
                last_stable_time = None
                oled.text("Status: Ready", 0, 40)
                oled.text("Add weight", 0, 55)
            
            # Only process new measurements if we haven't saved yet
            elif not SAVED:
                recent_weights.append(weight)
                
                # Keep only the last ~2 seconds of readings
                if len(recent_weights) > 10: 
                    recent_weights.pop(0)
                
                # Check for stability with tolerance
                if len(recent_weights) >= 5:
                    min_w = min(recent_weights)
                    max_w = max(recent_weights)
                    weight_range_g = (max_w - min_w) * 1000.0
                    
                    if weight_range_g < STABILITY_THRESHOLD_G:
                        if last_stable_time is None:
                            last_stable_time = time.time()
                        
                        stable_for = time.time() - last_stable_time
                        
                        oled.text(f"Stable: {stable_for:.1f}s", 0, 40)
                        oled.text(f"Range: {weight_range_g:.0f}g", 0, 55)

                        if stable_for >= STABILITY_DURATION_S:
                            stable_weight = sum(recent_weights) / len(recent_weights)
                            save_weight_data(stable_weight)
                            SAVED = True  # Mark that we've saved
                            recent_weights = []
                            last_stable_time = None
                            # Show saved message briefly
                            display_message("Saved!", "Remove weight", "to measure again", "", 1500)
                            continue
                    else:
                        last_stable_time = None
                        oled.text(f"Range: {weight_range_g:.0f}g", 0, 40)
                        oled.text("Unstable", 0, 55)
                else:
                    oled.text("Sampling...", 0, 40)
                    oled.text(f"Samples: {len(recent_weights)}", 0, 55)
            else:
                # We've already saved and weight isn't back to zero yet
                oled.text("Remove weight", 0, 40)
                oled.text("to measure again", 0, 55)

            oled.show()
        else:
            display_message("Reading Error", "Check Sensor", "", "", 1000)

        time.sleep_ms(50)  # Reduced from 100ms since debouncing is handled separately

if __name__ == "__main__":
    main()