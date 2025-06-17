import tkinter as tk
from tkinter import font as tkFont
from tkinter import ttk, filedialog, messagebox
import random
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import struct
import socket
import threading
import time
import csv
from ag_uc2_8 import PiezoUC28

# Create a lookup table for sin and cos values for angles in the range [0, 360] with 0.1 degree intervals
angles = [i * 0.1 for i in range(36001)]  # Generate angles from 0 to 360 with 0.1 degree steps (3601 values)
cos_lookup = [math.cos(math.radians(angle)) for angle in angles]
sin_lookup = [math.sin(math.radians(angle)) for angle in angles]

def on_closing():    
    plt.close('all')  # Close all matplotlib plots
    root.destroy()

class IntensityMapGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Fluorescence Scanning")
        self.root.geometry("1280x1024")

        self.group = 4
        self.count_rate = 0
        self.index_x = 0
        self.index_y = 0
        self.move_x_value = 0
        self.move_y_value = 0

        self.axes = ["X-", "X+", "Y-", "Y+"]
        self.step_amplitude = [ tk.StringVar(value="32"),
                                tk.StringVar(value="28"),
                                tk.StringVar(value="26"),
                                tk.StringVar(value="22")]
        self.step_amplitude_entries = [None, None, None, None]
        self.unit_step = [ tk.StringVar(value="1"),
                            tk.StringVar(value="1"),
                            tk.StringVar(value="1"),
                            tk.StringVar(value="1")]
        self.unit_step_entries = [None, None, None, None]
        self.num_step = [ tk.StringVar(value="100"),
                          tk.StringVar(value="100"),
                          tk.StringVar(value="100"),
                          tk.StringVar(value="100")]
        self.num_step_entries = [None, None, None, None]
        self.move_button = [None, None, None, None]
        self.scaling_factor = [ tk.StringVar(value="0.2"),
                                tk.StringVar(value="0.2"),
                                tk.StringVar(value="0.2"),
                                tk.StringVar(value="0.2")]
        self.scaling_factor_entries = [None, None, None, None]
        self.skew = tk.StringVar(value='0')
        self.scaling_locked = True

        self.is_running = False
        self.client1_thread = None
        self.client1_running = False
        self.client_socket1 = None

        self.arrial18 = tkFont.Font(family='Arial', size=18)
        self.setup_variables()

        # Create the notebook (tab structure)
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(expand=1, fill="both")
        self.style = ttk.Style()
        self.style.configure('TCombobox', font=self.arrial18)
        self.style.configure('TNotebook.Tab', font=self.arrial18)
        self.style.map('TNotebook.Tab',
                       background=[('selected', 'red')],
                       foreground=[('selected', 'blue')],
                       relief=[('selected', 'flat')])

        # Tab 1 - Main Scanning tab
        self.scan_tab = tk.Frame(self.tabs)
        self.tabs.add(self.scan_tab, text="Scan")

        # Tab 2 - Calibration tab
        self.calibration_tab = tk.Frame(self.tabs)
        self.tabs.add(self.calibration_tab, text="Calibration")

        # Build Scan Tab
        self.build_scan_tab()

        # Build Calibration Tab
        self.build_calibration_tab()
        
        self.piezo = PiezoUC28(1)
        self.piezo.discover_and_open_device()

    def setup_variables(self):
        self.is_running = False
        self.group = tk.IntVar(value=4)
        self.cursor_x = tk.StringVar(value='0.00')
        self.cursor_y = tk.StringVar(value='0.00')
        self.intensity = tk.StringVar(value='0')
        self.move_x = tk.StringVar(value='0.00')
        self.move_y = tk.StringVar(value='0.00')
        self.rotate = tk.StringVar(value='0.00')
        self.acq_time = tk.StringVar(value='100')
        self.step_z = tk.StringVar(value='5')
        self.step = tk.StringVar(value='0.5')
        self.frame = tk.StringVar(value='10')

        # Variables for server IPs and Ports
        self.server1_ip = tk.StringVar(value="192.168.236.2")
        self.server1_port = tk.IntVar(value=65053)

    def build_scan_tab(self):
        # Scan Tab GUI (moving the current layout to this tab)
        self.setup_plot()
        self.setup_controls()
        self.setup_bindings()

    def setup_plot(self):
        self.fig, self.ax = plt.subplots(figsize=(5, 5))
        frame_size = round(float(self.frame.get())/float(self.step.get()))

        self.default_intensity = np.zeros((frame_size, frame_size), dtype=int)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.scan_tab)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        extent = [-0.5, frame_size - 0.5, frame_size - 0.5, -0.5]
        #self.im = self.ax.imshow(self.default_intensity, cmap='hot')
        self.im = self.ax.imshow(self.default_intensity, cmap='hot', extent=extent, origin='upper')
        self.fig.colorbar(self.im)
        self.canvas.draw()
        self.crosshair, = self.ax.plot([], [], color='blue', marker='+', markeredgewidth=5, markersize=20)

    def setup_controls(self):
        self.button_frame = tk.Frame(self.scan_tab)
        self.button_frame.pack(side=tk.TOP, pady=10)
        self.start_button = tk.Button(self.button_frame, text="Start", bg="green", font=self.arrial18, command=self.toggle_plotting)
        self.start_button.pack(side=tk.LEFT, pady=10)        
        self.save_button = tk.Button(self.button_frame, text="Save", font=self.arrial18, command=self.save_data)
        self.save_button.pack(side=tk.LEFT, pady=10)

        self.setup_status_panel()
        self.setup_input_panel()
        self.setup_server_inputs()
        self.setup_z_buttons()

    def setup_status_panel(self):
        #status_frame = tk.Frame(self.root)
        status_frame = tk.Frame(self.scan_tab)
        status_frame.pack(side=tk.TOP, pady=10)
        tk.Label(status_frame, text="X:", font=self.arrial18).pack(side=tk.LEFT)
        self.x_label = tk.Label(status_frame, textvariable=self.cursor_x, font=self.arrial18)
        self.x_label.pack(side=tk.LEFT, padx=5)

        tk.Label(status_frame, text="Y:", font=self.arrial18).pack(side=tk.LEFT)
        self.y_label = tk.Label(status_frame, textvariable=self.cursor_y, font=self.arrial18)
        self.y_label.pack(side=tk.LEFT, padx=5)

        tk.Label(status_frame, text="Counts Rate:", font=self.arrial18).pack(side=tk.LEFT)
        self.counts_label = tk.Label(status_frame, textvariable=self.intensity, font=self.arrial18)
        self.counts_label.pack(side=tk.LEFT, padx=5)

    def setup_input_panel(self):
        #input_frame = tk.Frame(self.root)
        input_frame = tk.Frame(self.scan_tab)
        input_frame.pack(side=tk.TOP, pady=10)
        self.create_input(input_frame, "Offset X:", self.move_x)
        self.create_input(input_frame, "Offset Y:", self.move_y)
        self.create_input(input_frame, "Rotate:", self.rotate)
        self.create_input(input_frame, "Time (ms):", self.acq_time)
        self.create_input(input_frame, "Step (μm):", self.step)
        self.create_input(input_frame, "Frame (μm):", self.frame)

    def create_input(self, frame, label, var):
        tk.Label(frame, text=label, font=self.arrial18).pack(side=tk.LEFT)
        entry = tk.Entry(frame, textvariable=var, font=self.arrial18, width=5)
        entry.pack(side=tk.LEFT, padx=5)

    def setup_server_inputs(self):
        #server_frame = tk.Frame(self.root)
        server_frame = tk.Frame(self.scan_tab)
        server_frame.pack(side=tk.TOP, pady=10)

        # Server 1 IP and Port inputs
        tk.Label(server_frame, text="Picoquant IP:", font=self.arrial18).pack(side=tk.LEFT)
        server1_ip_entry = tk.Entry(server_frame, textvariable=self.server1_ip, font=self.arrial18, width=12)
        server1_ip_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(server_frame, text="Port:", font=self.arrial18).pack(side=tk.LEFT)
        server1_port_entry = tk.Entry(server_frame, textvariable=self.server1_port, font=self.arrial18, width=6)
        server1_port_entry.pack(side=tk.LEFT, padx=5)

    def setup_z_buttons(self):
        #z_button_frame = tk.Frame(self.root)
        z_button_frame = tk.Frame(self.scan_tab)
        z_button_frame.pack(side=tk.TOP, pady=10)

        self.create_input(z_button_frame, "Group:", self.group)

        self.z_minus_button = tk.Button(z_button_frame, text="Z-", font=self.arrial18, command=lambda: self.send_zm(self.z_minus_button))
        self.z_minus_button.pack(side=tk.LEFT, padx=5)

        self.z_plus_button = tk.Button(z_button_frame, text="Z+", font=self.arrial18, command=lambda: self.send_zp(self.z_plus_button))
        self.z_plus_button.pack(side=tk.LEFT, padx=5)

        self.create_input(z_button_frame, "Step Z:", self.step_z)

    def setup_bindings(self):
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.canvas.mpl_connect("motion_notify_event", self.on_drag)

    def toggle_plotting(self):
        if not self.client1_running:
            # Start client 1
            self.client1_thread = threading.Thread(target=self.tcp_client1, daemon=True)
            self.client1_thread.start()
            self.client1_running = True

            self.start_button.config(text="Running", font=self.arrial18, bg="red")
            self.is_running = True  # Data sending should now be active
        else:
            # Toggle between Start/Stop without reconnecting the servers
            self.send_stop_to_server1()
            self.client1_running = False
            self.is_running = not self.is_running
            self.piezo.set_local_mode()

            # Update the button label depending on the current state
            self.start_button.config(text="Start", font=self.arrial18, bg="green")

    def build_calibration_tab(self):
        self.lock_button = tk.Button(self.calibration_tab, text="Unlock", font=self.arrial18, width=6, command=lambda: self.toggle_scaling_lock()).grid(row=0, column=0, padx=0, pady=5, sticky="nsew")
        tk.Label(self.calibration_tab, text="Step Amplitude", width = 12, font=self.arrial18).grid(row=1, column=0, padx=0, pady=5, sticky="e")
        tk.Label(self.calibration_tab, text="Unit Steps", width = 12, font=self.arrial18).grid(row=2, column=0, padx=0, pady=5, sticky="e")
        tk.Label(self.calibration_tab, text="N# Unit Steps", width = 12, font=self.arrial18).grid(row=3, column=0, padx=0, pady=5, sticky="e")
        tk.Label(self.calibration_tab, text="Scaling Factor", width = 12, font=self.arrial18).grid(row=5, column=0, padx=0, pady=5, sticky="e")

        for i, axis in enumerate(self.axes):
            tk.Label(self.calibration_tab, text=axis, width = 3, font=self.arrial18).grid(row=0, column=i+1, padx=10, pady=5, sticky="nsew")
            self.step_amplitude_entries[i] = tk.Entry(self.calibration_tab, textvariable=self.step_amplitude[i], font=self.arrial18, width=3)
            self.step_amplitude_entries[i].grid(row=1, column=i+1, padx=10, pady=5, sticky="nsew")
            self.step_amplitude_entries[i].config(state='disabled')

            self.unit_step_entries[i] = tk.Entry(self.calibration_tab, textvariable=self.unit_step[i], font=self.arrial18, width=3)
            self.unit_step_entries[i].grid(row=2, column=i+1, padx=10, pady=5, sticky="nsew")
            self.unit_step_entries[i].config(state='disabled')

            self.num_step_entries[i] = tk.Entry(self.calibration_tab, textvariable=self.num_step[i], font=self.arrial18, width=3)
            self.num_step_entries[i].grid(row=3, column=i+1, padx=10, pady=5, sticky="nsew")
            self.num_step_entries[i].config(state='disabled')

            self.move_button[i] = tk.Button(self.calibration_tab, text="Go", font=self.arrial18, width=3, command=lambda i=i: self.calib_move(i))
            self.move_button[i].grid(row=4, column=i+1, padx=10, pady=5, sticky="nsew")
            self.move_button[i].config(state='disabled')

            self.scaling_factor_entries[i] = tk.Entry(self.calibration_tab, textvariable=self.scaling_factor[i], font=self.arrial18, width=3)
            self.scaling_factor_entries[i].grid(row=5, column=i+1, padx=10, pady=5, sticky="nsew")
            self.scaling_factor_entries[i].config(state='disabled')

        tk.Label(self.calibration_tab, text="Skew Correction", width = 12, font=self.arrial18).grid(row=6, column=0, padx=0, pady=5, sticky="e")
        self.skew_entries = tk.Entry(self.calibration_tab, textvariable=self.skew, font=self.arrial18, width=3)
        self.skew_entries.grid(row=6, column=1, padx=10, pady=5, sticky="nsew")
        self.skew_entries.config(state='disabled')

    def toggle_scaling_lock(self):
        if self.scaling_locked:
            self.scaling_locked = False
            #self.lock_button.config(text="Lock")
            for i, axis in enumerate(self.axes):
                self.step_amplitude_entries[i].config(state='normal')
                self.unit_step_entries[i].config(state='normal')
                self.num_step_entries[i].config(state='normal')
                self.move_button[i].config(state='normal')
                self.scaling_factor_entries[i].config(state='normal')
                self.skew_entries.config(state='normal')
        else:
            self.scaling_locked = True
            #self.lock_button.config(text="Unlock")
            for i, axis in enumerate(self.axes):
                self.step_amplitude_entries[i].config(state='disabled')
                self.unit_step_entries[i].config(state='disabled')
                self.num_step_entries[i].config(state='disabled')
                self.move_button[i].config(state='disabled')
                self.scaling_factor_entries[i].config(state='disabled')
                self.skew_entries.config(state='disabled')
                self.piezo.set_remote_mode()
                self.piezo.set_channel()
                if i == 0:
                    self.piezo.set_step_amplitude_negative(1,int(self.step_amplitude[i].get()))
                elif i == 1:
                    self.piezo.set_step_amplitude_positive(1,int(self.step_amplitude[i].get()))
                elif i == 2:
                    self.piezo.set_step_amplitude_negative(2,int(self.step_amplitude[i].get()))
                elif i == 3:
                    self.piezo.set_step_amplitude_positive(2,int(self.step_amplitude[i].get()))
                self.piezo.set_local_mode()

    def calib_move(self, i):
        acq_time = int(self.acq_time.get()) / 1000
        num_iterations = int(self.num_step[i].get())
        self.piezo.set_remote_mode()
        self.piezo.set_channel()
        if i == 0:
            self.piezo.set_step_amplitude_negative(1,int(self.step_amplitude[i].get()))
            for _ in range(num_iterations):
                self.piezo.relative_move(1, -1*int(self.unit_step[i].get()))
                #self.piezo.jogging(1, -1*int(self.unit_step[i].get()))
                #self.piezo.stop_motion(1)
                time.sleep(acq_time)
        elif i == 1:
            self.piezo.set_step_amplitude_positive(1,int(self.step_amplitude[i].get()))
            for _ in range(num_iterations):
                self.piezo.relative_move(1, int(self.unit_step[i].get()))
                #self.piezo.jogging(1, int(self.unit_step[i].get()))
                #self.piezo.stop_motion(1)
                time.sleep(acq_time)
        elif i == 2:
            self.piezo.set_step_amplitude_negative(2,int(self.step_amplitude[i].get()))
            for _ in range(num_iterations):
                self.piezo.relative_move(2, -1*int(self.unit_step[i].get()))
                #self.piezo.jogging(2, -1*int(self.unit_step[i].get()))
                #self.piezo.stop_motion(2)
                time.sleep(acq_time)
        elif i == 3:
            self.piezo.set_step_amplitude_positive(2,int(self.step_amplitude[i].get()))
            for _ in range(num_iterations):
                self.piezo.relative_move(2, int(self.unit_step[i].get()))
                #self.piezo.jogging(2, int(self.unit_step[i].get()))
                #self.piezo.stop_motion(2)
                time.sleep(acq_time)
        self.piezo.set_local_mode()

    def step_to_distance_x(self, step):
        """Convert steps to micrometers."""
        return step * float(self.scaling_factor[2].get())

    def distance_to_step_x(self, distance):
        """Convert micrometers to steps."""
        return distance / float(self.scaling_factor[2].get())

    def step_to_distance_y(self, step):
        """Convert steps to micrometers."""
        return step * float(self.scaling_factor[1].get())

    def distance_to_step_y(self, distance):
        """Convert micrometers to steps."""
        return distance / float(self.scaling_factor[1].get())
        # TCP client 1 function
    def tcp_client1(self):
        cnt = 0
        group = int(self.group.get())
        move_x = float(self.move_x.get())
        move_y = float(self.move_y.get())
        frame_size = round(float(self.frame.get())/float(self.step.get()))
        step_x = round(self.distance_to_step_x(float(self.step.get())))
        step_y = round(self.distance_to_step_y(float(self.step.get())))
        acq_time = int(self.acq_time.get()) / 1000  # Convert ms to seconds
        self.piezo.set_remote_mode()
        self.piezo.set_channel()

        try:
            if not self.client_socket1:
                self.client_socket1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket1.connect((self.server1_ip.get(), int(self.server1_port.get())))
                #print("Connected to Nanonis TCP/IP")
            self.send_start_to_server1(int(self.acq_time.get()))
            self.piezo.set_step_amplitude_negative(1,int(self.step_amplitude[0].get()))
            self.piezo.set_step_amplitude_positive(1,int(self.step_amplitude[1].get()))
            self.piezo.set_step_amplitude_negative(2,int(self.step_amplitude[2].get()))
            self.piezo.set_step_amplitude_positive(2,int(self.step_amplitude[3].get()))
            time.sleep(acq_time*10)
            
            while self.client1_running:
                #print("tcp_client1 is running")
                if self.is_running:
                    for y in range(frame_size):
                        self.index_y = y
                        if y == 0:
                            # Apply calibration and rotation for initial positioning
                            move_x_value = self.distance_to_step_x(move_x - (float(self.frame.get())/2))
                            move_y_value = self.distance_to_step_y((float(self.frame.get())/2) - move_y)
                            move_x_corr, move_y_corr = self.skew_and_rotation(-move_x_value, move_y_value)
                            #self.piezo.relative_move(2, round(move_x_corr))
                            #self.piezo.relative_move(1, round(move_y_corr))
                            self.move_to(move_x_corr, move_y_corr, step_x, step_y)
                            #print("X: 0" + " Y: " + str(y))
                        else: 
                            _, step_y_corr = self.skew_and_rotation(0, -step_y)
                            self.piezo.relative_move(1, round(step_y_corr))
                            #print("Y: " + str(y))
                        if not self.client1_running:
                            break
                        
                        if y % 2 == 0:
                            x_range = range(frame_size)  # Left to Right
                        else:
                            x_range = range(frame_size-1, -1, -1)  # Right to Left (Zig-Zag)

                        for x in x_range:
                            if not self.client1_running:
                                break
                            self.index_x = x
                            self.cursor_x.set(f"{self.step_to_distance_x((x - frame_size/2)*step_x):.1f}")
                            self.cursor_y.set(f"{self.step_to_distance_y((frame_size/2 - y)*step_y):.1f}")
                            
                            if y % 2 == 0: # Left to Right
                                if x != 0:
                                    step_x_corr, _ = self.skew_and_rotation(-step_x, 0)
                                    self.piezo.relative_move(2, round(step_x_corr))
                                    #print("X: " + str(x))
                                    
                            else: # Right to Left
                                if frame_size-1-x != 0:
                                    step_x_corr, _ = self.skew_and_rotation(step_x, 0)
                                    self.piezo.relative_move(2, round(step_x_corr))
                                    #print("X: " + str(x))
                            # After sending X,Y data, trigger tcp_client2
                            time.sleep(acq_time)
                            #self.update_plot(x, y, random.randrange(1,100))
                            self.read_apd(x, y)

                    self.update_crosshair(x, y)
                    self.send_stop_to_server1()
                    self.piezo.set_local_mode()
                    self.start_button.config(text="Start", font=self.arrial18, bg="green")
                    self.client1_running = False
        except Exception as e:
            print(f"Client 1 error: {e}")

    def read_apd(self, x, y):
        message = f"D".encode('utf-8') 
        try:
            # Send data only if running
            if self.client1_running:
                self.client_socket1.sendall(message)
                #print(f"Send: {message}")
                data = b''
                while len(data) < 4:
                    packet = self.client_socket1.recv(4 - len(data))
                    if not packet:
                        raise ConnectionError("Socket connection broken")
                    data += packet

                # Unpack the received data (intensity value)
                intensity_value = struct.unpack('!I', data)[0]

                # Update the plot with the received intensity value for the given (x, y)
                self.update_plot(x, y, int(intensity_value))
                self.intensity.set(self.format_intensity(intensity_value))
         
        except Exception as e:
            print(f"Client 2 error: {e}")

    def format_intensity(self, value):
        """Format an integer into a human-readable string with K or M suffix."""
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f} MCps"  # Display in millions with one decimal place
        elif value >= 1_000:
            return f"{value / 1_000:.1f} KCps"  # Display in thousands with one decimal place
        else:
            return str(value) + " Cps" # Display as is if less than 1000

    def send_start_to_server1(self, binwidth):
        message = f"M{binwidth}M".encode('utf-8')
        try:
            if self.client1_running:
                self.client_socket1.sendall(message)
                receive = self.client_socket1.recv(1024).decode('utf-8')
        except Exception as e:
            print(f"Error sending 'Start' to server1: {e}")

    def send_stop_to_server1(self):
        message = f"S".encode('utf-8')
        try:
            if self.client1_running:
                # Send "Stop" message to server2
                self.client_socket1.sendall(message)
                receive = self.client_socket1.recv(1024).decode('utf-8')
                #print("Sent 'Stop' to server2")
        except Exception as e:
            print(f"Error sending 'Stop' to server1: {e}")

    def update_plot(self, x, y, intensity_value):
        if self.is_running:
            # Run all updates on the main thread to avoid RuntimeErrors with Tkinter
            if not self.canvas.get_tk_widget().winfo_exists():
                return  # Exit if the Tkinter widget is not fully initialized

            # Calculate frame size from user input
            frame_size = round(float(self.frame.get())/float(self.step.get()))

            # Check if the frame size has changed; if so, update the intensity data array and extent
            if not hasattr(self, 'current_frame_size') or self.current_frame_size != frame_size:
                self.current_frame_size = frame_size  # Store the new frame size

                # Reset intensity data with the updated frame size
                new_intensity_data = np.zeros((frame_size, frame_size))
                extent = [-0.5, frame_size - 0.5, frame_size - 0.5, -0.5]
                self.im.set_data(new_intensity_data)  # Update the data
                self.im.set_extent(extent)  # Set new extent to resize properly

                # Clear and reattach crosshair and any other plot elements if necessary
                self.crosshair.set_data([], [])  # Clear crosshair initially

            # Update the specific pixel in intensity data
            intensity_data = self.im.get_array()
            intensity_data[y, x] = intensity_value
            self.im.set_data(intensity_data)

            # Update color scaling for the new data range
            self.im.set_clim(vmin=np.min(intensity_data), vmax=np.max(intensity_data))

            # Redraw only if we're in the main thread
            self.canvas.draw_idle()  # Use draw_idle instead of draw to minimize threading issues

    def on_click(self, event):
        if event.inaxes:
            # Get the current frame size (i.e., resolution)
            frame_size = self.im.get_array().shape[0]
            #step = self.distance_to_step(float(self.step.get()))

            # Clamp the coordinates within valid bounds
            x = round(min(max(event.xdata, 0), frame_size - 1))
            y = round(min(max(event.ydata, 0), frame_size - 1))

            step_x = round(self.distance_to_step_x(float(self.step.get())))
            step_y = round(self.distance_to_step_y(float(self.step.get())))
            delta_x = self.distance_to_step_x((self.index_x - x)*(float(self.step.get())))
            delta_y = self.distance_to_step_y((self.index_y - y)*(float(self.step.get())))
            delta_x, delta_y = self.skew_and_rotation(delta_x, delta_y)
            self.index_x = x
            self.index_y = y
            #print("Cursor move")
            #print("Move x:",delta_x)
            #print("Move y:",delta_y)
            self.piezo.set_remote_mode()
            self.piezo.set_channel()
            #self.piezo.relative_move(2,round(delta_x))
            #self.piezo.relative_move(1,round(delta_y))
            self.move_to(delta_x, delta_y, step_x, step_y)
            self.piezo.set_local_mode()

            # Update the crosshair and the cursor positions safely
            self.update_crosshair(x, y)

    def move_to(self, x, y, step_x, step_y):
        range_x = round(abs(x)/step_x)
        range_y = round(abs(y)/step_y)
        sign_x = np.sign(x)
        sign_y = np.sign(y)
        acq_time = int(self.acq_time.get()) / 1000  # Convert ms to seconds
        for x in range(range_x):
            self.piezo.relative_move(2,round(sign_x*(step_x)))
            time.sleep(acq_time)
        for y in range(range_y):
            self.piezo.relative_move(1,round(sign_y*(step_y)))
            time.sleep(acq_time)

    def on_drag(self, event):
        if event.inaxes and event.button == 1:  # Left click drag
            # Get the current frame size (i.e., resolution)
            frame_size = self.im.get_array().shape[0]

            # Clamp the coordinates within valid bounds
            x = round(min(max(event.xdata, 0), frame_size - 1))
            y = round(min(max(event.ydata, 0), frame_size - 1))
            
            # Update the crosshair and the cursor positions safely
            self.update_crosshair(x, y)

    def update_crosshair(self, x, y):
        # Set the crosshair position to the clamped coordinates
        self.crosshair.set_data([x], [y])

        # Update cursor x, y, and intensity values
        frame_size = self.im.get_array().shape[0]/2
        step_x = self.distance_to_step_x(float(self.step.get()))
        step_y = self.distance_to_step_y(float(self.step.get()))
        self.cursor_x.set(f"{self.step_to_distance_x((x - frame_size)*step_x):.1f}")
        self.cursor_y.set(f"{self.step_to_distance_y((frame_size - y)*step_y):.1f}")
        self.intensity.set(self.format_intensity(self.im.get_array()[y, x]))

        # Redraw the canvas with updated crosshair
        self.canvas.draw()

    def send_zm(self, button):
        move_z_value = int(self.step_z.get())
        group = int(self.group.get())
        message = None
        message = self.send_move_command(direction="Z-",steps=move_z_value,group=group)
        
    def send_zp(self, button):
        move_z_value = int(self.step_z.get())
        group = int(self.group.get())
        message = None
        message = self.send_move_command(direction="Z-+",steps=move_z_value,group=group)

    def skew_and_rotation(self, x, y):
        # Step 1: Calibration to make axes perpendicular
        x_calibrated = x - math.radians(float(self.skew.get()))
        y_calibrated = y

        # Step 2: Apply the user-specified rotation
        x_final = x_calibrated * self.lookup_cos(float(self.rotate.get())) - y_calibrated * self.lookup_sin(float(self.rotate.get()))
        y_final = x_calibrated * self.lookup_sin(float(self.rotate.get())) + y_calibrated * self.lookup_cos(float(self.rotate.get()))
        
        return x_final, y_final

    # Function to access the lookup table for cos and sin
    def lookup_cos(self, angle):
        # Ensure angle is within the valid range [0, 360)
        angle = round(angle,2) % 360
        index = int(angle * 100)  # Multiply by 10 to shift the decimal
        return cos_lookup[index]

    def lookup_sin(self, angle):
        # Ensure angle is within the valid range [0, 360)
        angle = round(angle,2) % 360
        index = int(angle * 100)  # Multiply by 10 to shift the decimal
        return sin_lookup[index]

    def save_data(self):
        filename = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("TXT files", "*.txt")])

        if filename:
            try:
                intensity_data = self.im.get_array()
                with open(filename, 'w') as f1:
                    writer = csv.writer(f1, delimiter='\t')
                    writer.writerows(intensity_data)
            except Exception as e:
                print(f"Error saving data: {e}")
 
if __name__ == "__main__":
    root = tk.Tk()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    app = IntensityMapGUI(root)
    root.mainloop()
