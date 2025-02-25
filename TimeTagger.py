from snAPI.Main import *
import snAPI.Main as snp
import numpy as np 
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import struct
import socket
import select
import threading
import random
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv

def on_closing():
    plt.close('all')  # Close all matplotlib plots
    root.destroy()

class MeasurementApp:
    def __init__(self, root):
        
        self.root = root
        self.root.title("Time Tagger App")
        self.root.geometry("1600x1280")
        
        # Set font to Arial 18 for all widgets
        self.arr18 = ('Arial', 18)
        self.style = ttk.Style()
        self.style.configure('TLabel', font=self.arr18)
        self.style.configure('TEntry', font=self.arr18)
        self.style.configure('TButton', font=self.arr18)
        self.style.configure('TCombobox', font=self.arr18)

        self.server_socket = None
        self.client_socket = None
        self.server_thread = False
        self.server_running = False
        
        # Initialize Picoquant
        self.sn = snp.snAPI()
        self.sn.getDevice()
        self.sn.initDevice(MeasMode.T2)

        # Initialize data storage
        self.data = {"time_trace": [], "histogram": [], "correlation": []}
        
        self.entries={}
        
        # Initialize data storage
        self.data = {"time_trace": [], "histogram": [], "correlation": []}
        self.default_trigger_mode = "Rising Edge"
        self.default_trigger_level = "600"
        self.default_offset = "0"
        self.default_port_number = "65053"
        self.default_bin_width = "100"
        self.default_window_size = "10"
        self.default_acquisition_time = "2000000000"
        self.default_ref_channel = "Sync"
        self.default_start_channel = "Channel 1"
        self.default_stop_channel = "Channel 2"

        self.time_trace_running = False
        
        self.ip_address = socket.gethostbyname(socket.gethostname())
        
        self.default_trigger_mode 
        # Create the notebook (tabbed interface)
        notebook = ttk.Notebook(self.root)
        notebook.pack(expand=1, fill="both")        
        
        # Style configuration
        self.style = ttk.Style()
        self.style.configure('TCombobox', font=self.arr18)
        self.style.configure('TNotebook.Tab', font=self.arr18)

        self.style.map('TNotebook.Tab',
                       background=[('selected', 'red')],
                       foreground=[('selected', 'blue')],
                       relief=[('selected', 'flat')])
        
        # Create the tabs
        self.create_configuration_tab(notebook)
        self.create_time_trace_tab(notebook)
        self.create_histogram_tab(notebook)
        self.create_correlation_tab(notebook)
        
    def create_configuration_tab(self, notebook):
        config_frame = ttk.Frame(notebook)
        notebook.add(config_frame, text="Configurations")
        
        labels = ["Sync", "Channel 1", "Channel 2", "Channel 3", "Channel 4"]

        self.entries = {}  # Store entries for later access
        row = 2

        trigger_label = ttk.Label(config_frame, text="Trigger Mode")
        trigger_label.grid(row=1, column=1, padx=10, pady=5)
     
        voltage_label = ttk.Label(config_frame, text="Trigger Level (mV)")
        voltage_label.grid(row=1, column=2, padx=10, pady=5)
        
        offset_label = ttk.Label(config_frame, text="Offset (ps)")
        offset_label.grid(row=1, column=3, padx=10, pady=5)
        
        for label_text in labels:
            ttk.Label(config_frame, text=label_text).grid(row=row, column=0, padx=10, pady=5, sticky="w")
            
            # Trigger Mode
            trigger_mode = ttk.Combobox(config_frame, values=["Rising Edge", "Falling Edge"], font=self.arr18)
            trigger_mode.grid(row=row, column=1, padx=5, pady=5)
            trigger_mode.set(self.default_trigger_mode)
            
            # Trigger Level
            trigger_level = ttk.Entry(config_frame, font=self.arr18)
            trigger_level.grid(row=row, column=2, padx=5, pady=5)
            trigger_level.insert(0, self.default_trigger_level)
            
            # Offset
            offset = ttk.Entry(config_frame, font=self.arr18)
            offset.grid(row=row, column=3, padx=5, pady=5)
            offset.insert(0, self.default_offset)
            
            # Enable Button
            enable_button = tk.Button(config_frame, text="Enable/Disable", bg="orange", fg="white", width=15, font=self.arr18)
            enable_button.config(command=lambda  b=enable_button, tm=trigger_mode, tl=trigger_level, off=offset, label=label_text: self.toggle_enable(b, tm, tl, off, label))
            enable_button.grid(row=row, column=4, padx=10, pady=5)        # Store the entries in a dictionary for later access
        
            self.entries[label_text] = {
                "trigger_mode": trigger_mode,
                "trigger_level": trigger_level,
                "offset": offset
            }
            
            row += 1
        
        # TCP/IP Settings
        #ip_address = socket.gethostbyname(socket.gethostname())
        ttk.Label(config_frame, text=f"IP: {self.ip_address}").grid(row=row, column=0, padx=10, pady=5, sticky="w")

        tcp_enable_button = tk.Button(config_frame, text="Enable/Disable TCP/IP", bg="orange", fg="white", width=20, font=self.arr18, command=lambda: self.toggle_tcp_enable(tcp_enable_button))
        tcp_enable_button.grid(row=row, column=1, padx=10, pady=5)

        port_label = ttk.Label(config_frame, text="Port Number")
        port_label.grid(row=row, column=2, padx=10, pady=5, sticky="w")

        port_number = ttk.Entry(config_frame, font=self.arr18)
        port_number.grid(row=row, column=3, padx=10, pady=5)
        port_number.insert(0, self.default_port_number)

        self.entries.update({
            "port_number": port_number,
        })

    def create_time_trace_tab(self, notebook):
        time_trace_frame = ttk.Frame(notebook)
        notebook.add(time_trace_frame, text="Time Trace")

        # Input fields
        ttk.Label(time_trace_frame, text="Number of Bins:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        tt_bin_width = ttk.Entry(time_trace_frame, font=self.arr18)
        tt_bin_width.grid(row=1, column=0, padx=100, pady=5)
        tt_bin_width.insert(0, self.default_bin_width)

        ttk.Label(time_trace_frame, text="Window Size (s):").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        tt_window_size = ttk.Entry(time_trace_frame, font=self.arr18)
        tt_window_size.grid(row=2, column=0, padx=100, pady=5)
        tt_window_size.insert(0, self.default_window_size)

        ttk.Label(time_trace_frame, text="Acquisition Time (ms):").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        tt_acquisition_time = ttk.Entry(time_trace_frame, font=self.arr18)
        tt_acquisition_time.grid(row=3, column=0, padx=100, pady=5)
        tt_acquisition_time.insert(0, self.default_acquisition_time)
        
        self.entries.update({
            "tt_bin_width": tt_bin_width,
            "tt_window_size": tt_window_size,
            "tt_acquisition_time": tt_acquisition_time
        })

        # Start/Stop Button
        self.time_trace_button = tk.Button(time_trace_frame, text="Start", bg="green", fg="white", width=10, font=self.arr18, command=lambda: self.toggle_start(self.time_trace_button, "time_trace"))
        self.time_trace_button.grid(row=4, column=0, columnspan=2, padx=10, pady=10)

        # Plot area (scaled by 2)
        self.fig_time_trace, self.ax_time_trace = plt.subplots(figsize=(15, 9))
        self.canvas_time_trace = FigureCanvasTkAgg(self.fig_time_trace, master=time_trace_frame)
        self.canvas_time_trace.get_tk_widget().grid(row=5, column=0, columnspan=2, padx=10, pady=10)   
        
        # Save button
        self.time_trace_save = tk.Button(time_trace_frame, text="Save Data", bg="blue", fg="white", font=self.arr18, command=lambda: self.save_data("time_trace"))
        self.time_trace_save.grid(row=6, column=0, columnspan=2, padx=10, pady=10)
    
    def create_histogram_tab(self, notebook):
        histogram_frame = ttk.Frame(notebook)
        notebook.add(histogram_frame, text="Histogram")
        
        # Input fields        
        ttk.Label(histogram_frame, text="Reference Channel:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        hist_ref_channel = ttk.Combobox(histogram_frame, values=["Sync", "Channel 1", "Channel 2", "Channel 3", "Channel 4"], font=self.arr18)
        hist_ref_channel.grid(row=1, column=0, padx=100, pady=5)
        hist_ref_channel.insert(0, self.default_ref_channel)
        
        ttk.Label(histogram_frame, text="Bin Width (ps):").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        hist_bin_width = ttk.Entry(histogram_frame, font=self.arr18)
        hist_bin_width.grid(row=2, column=0, padx=100, pady=5)
        hist_bin_width.insert(0, self.default_bin_width)
        
        ttk.Label(histogram_frame, text="Acquisition Time (s):").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        hist_acquisition_time = ttk.Entry(histogram_frame, font=self.arr18)
        hist_acquisition_time.grid(row=3, column=0, padx=100, pady=5)
        hist_acquisition_time.insert(0, self.default_acquisition_time)
        
        self.entries.update({
            "hist_ref_channel": hist_ref_channel,
            "hist_bin_width": hist_bin_width,
            "hist_acquisition_time": hist_acquisition_time
        })
        
        # Start/Stop Button
        self.histogram_button = tk.Button(histogram_frame, text="Start", bg="green", fg="white", width=10, font=self.arr18, command=lambda: self.toggle_start(self.histogram_button, "histogram"))
        self.histogram_button.grid(row=4, column=0, columnspan=2, padx=10, pady=10)
        
        # Plot area (scaled by 2)
        self.fig_histogram, self.ax_histogram = plt.subplots(figsize=(15, 9))
        self.canvas_histogram = FigureCanvasTkAgg(self.fig_histogram, master=histogram_frame)
        self.canvas_histogram.get_tk_widget().grid(row=5, column=0, columnspan=2, padx=10, pady=10)
        
        # Save button
        self.histogram_save = tk.Button(histogram_frame, text="Save Data", bg="blue", fg="white", font=self.arr18, command=lambda: self.save_data("histogram"))
        self.histogram_save.grid(row=6, column=0, columnspan=2, padx=10, pady=10)
        
    def create_correlation_tab(self, notebook):
        correlation_frame = ttk.Frame(notebook)
        notebook.add(correlation_frame, text="Correlation")
        
        # Input fields
        ttk.Label(correlation_frame, text="Start Channel:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        cor_start_channel = ttk.Combobox(correlation_frame, values=["Channel 1", "Channel 2", "Channel 3", "Channel 4"], font=self.arr18)
        cor_start_channel.grid(row=1, column=0, padx=100, pady=5)
        cor_start_channel.insert(0, self.default_start_channel)
        
        ttk.Label(correlation_frame, text="Stop Channel:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        cor_stop_channel = ttk.Combobox(correlation_frame, values=["Channel 1", "Channel 2", "Channel 3", "Channel 4"], font=self.arr18)
        cor_stop_channel.grid(row=2, column=0, padx=100, pady=5)
        cor_stop_channel.insert(0, self.default_stop_channel)
        
        ttk.Label(correlation_frame, text="Bin Width (ps):").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        cor_bin_width = ttk.Entry(correlation_frame, font=self.arr18)
        cor_bin_width.grid(row=3, column=0, padx=100, pady=5)
        cor_bin_width.insert(0, self.default_bin_width)
        
        ttk.Label(correlation_frame, text="Window Size (ps):").grid(row=4, column=0, padx=10, pady=5, sticky="w")
        cor_window_size = ttk.Entry(correlation_frame, font=self.arr18)
        cor_window_size.grid(row=4, column=0, padx=100, pady=5)
        cor_window_size.insert(0, self.default_window_size)

        ttk.Label(correlation_frame, text="Acquisition Size (s):").grid(row=5, column=0, padx=10, pady=5, sticky="w")
        cor_acquisition_time = ttk.Entry(correlation_frame, font=self.arr18)
        cor_acquisition_time.grid(row=5, column=0, padx=100, pady=5)
        cor_acquisition_time.insert(0, self.default_acquisition_time)

        self.entries.update({
            "cor_start_channel": cor_start_channel,
            "cor_stop_channel": cor_stop_channel,
            "cor_bin_width": cor_bin_width,
            "cor_window_size": cor_window_size,
            "cor_acquisition_time": cor_acquisition_time
        })
        
        # Start/Stop Button
        self.correlation_button = tk.Button(correlation_frame, text="Start", bg="green", fg="white", width=10, font=self.arr18, command=lambda: self.toggle_start(self.correlation_button, start_channel, stop_channel, bin_width, window_size,acquisition_time, "correlation"))
        self.correlation_button.grid(row=6, column=0, columnspan=2, padx=10, pady=10)
        
        # Plot area (scaled by 2)
        self.fig_correlation, self.ax_correlation = plt.subplots(figsize=(15, 9))
        self.canvas_correlation = FigureCanvasTkAgg(self.fig_correlation, master=correlation_frame)
        self.canvas_correlation.get_tk_widget().grid(row=7, column=0, columnspan=2, padx=10, pady=10)
        
        # Save button
        self.correlation_save = tk.Button(correlation_frame, text="Save Data", bg="blue", fg="white", font=self.arr18, command=lambda: self.save_data("correlation"))
        self.correlation_save.grid(row=8, column=0, columnspan=2, padx=10, pady=10)

    # Function to start the TCP/IP server
    def start_tcp_server(self, port):
        if self.server_running:
            #print("Server is already running.")
            return  # Prevent multiple instances

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind((self.ip_address, port))
            self.server_socket.listen(5)
            self.server_running = True
            self.allow_connections = True
            print(f"TCP/IP Server started on port {port}")

            # Start server loop in a separate thread
            server_thread = threading.Thread(target=self.server_loop, daemon=True)
            server_thread.start()
        except Exception as e:
            print(f"Error starting server: {e}")

    def server_loop(self):
        while self.server_running:
            if not self.allow_connections:
                time.sleep(1)  # Prevents unnecessary CPU usage
                continue  # Skip accepting new clients

            ready, _, _ = select.select([self.server_socket], [], [], 2.0)
            if ready:
                try:
                    self.client_socket, addr = self.server_socket.accept()
                    print(f"Connection from {addr}")
                    self.client_socket.settimeout(5.0)
                    self.handle_client()
                except socket.error as e:
                    print(f"Error accepting client: {e}")

    def handle_client(self):
        try:
            while self.server_running and self.allow_connections:
                ready_client, _, _ = select.select([self.client_socket], [], [], 2.0)
                if ready_client:
                    prefix = self.client_socket.recv(1).decode('utf-8')
                    if not prefix:
                        print("Client disconnected")
                        break

                    if prefix == 'M':
                        #print("M_command")
                        self.handle_M_command()
                    elif prefix == 'D':
                        #print("D_command")
                        self.handle_D_command()
                    elif prefix == 'S':
                        #print("S_command")
                        self.handle_S_command()
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            print(f"Client error: {e}")
        finally:
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None

    def handle_M_command(self):
        # Explicitly stop all ongoing activities and update button states
        self.stop_measurement("time_trace")
        self.stop_measurement("histogram")
        self.stop_measurement("correlation")
        # Update buttons to reflect stopped state
        self.time_trace_button.config(text="Start", bg="green")
        self.histogram_button.config(text="Start", bg="green")
        self.correlation_button.config(text="Start", bg="green")

        number_data = bytearray()
        while True:
            byte = self.client_socket.recv(1)
            if byte.decode('utf-8') == 'M':  # stop reading at non-digit or connection end  
                break
            number_data.extend(byte)
        number_str = int(number_data.decode('utf-8').strip())
        window = float(number_str / 20)
        time.sleep(0.5)
        self.sn.timeTrace.setNumBins(100)
        self.sn.timeTrace.setHistorySize(window)
        self.sn.timeTrace.measure(int(self.entries["tt_acquisition_time"].get()), waitFinished=False, savePTU=False)
        self.client_socket.sendall(b'OK')

    def handle_D_command(self):
        counts, times = self.sn.timeTrace.getData()
        self.client_socket.sendall(struct.pack('!I', int(counts[1][-1])))

    def handle_S_command(self):
        self.stop_measurement("time_trace")
        self.client_socket.sendall(b'OK')

    # Toggle function that starts or stops the TCP/IP server based on the button state
    def toggle_tcp_enable(self, button):

        if not self.server_running:
            # First time clicking: Start the server
            port_number = int(self.entries["port_number"].get())  # Read port from UI
            self.start_tcp_server(port_number)
            button.config(text="Enable TCP/IP", bg="green")
            self.allow_connections = True
        else:
            # Toggle client connection permissions
            if self.allow_connections:
                button.config(text="Disable TCP/IP", bg="red")
                self.allow_connections = False  # Block new client connections
            else:
                button.config(text="Enable TCP/IP", bg="green")
                self.allow_connections = True   # Allow new clients to connect

    def toggle_enable(self, button, trigger_mode, trigger_level, offset, label):
        # Convert label to numeric value using the dictionary
        # Dictionary to map label to corresponding numeric value
        label_map = {
            "Channel 1": 0,
            "Channel 2": 1,
            "Channel 3": 2,
            "Channel 4": 3
        }

        label_value = label_map.get(label, -1)  # Default to -1 if label is not found
        tm_value = 1 if trigger_mode.get() == "Rising Edge" else 0
        tl_value = trigger_level.get()
        off_value = offset.get()
    
        if label == "Sync":
            self.sn.device.setSyncEdgeTrig(int(tl_value), tm_value)
            self.sn.device.setSyncChannelOffset(label_value, int(off_value))
        else:
            self.sn.device.setInputEdgeTrig(label_value, int(tl_value), tm_value)
            self.sn.device.setInputChannelOffset(label_value, int(off_value))

        if button["text"] == "Enable":
            button.config(text="Disable", bg="red")
            if label == "Sync":
                self.sn.device.setSyncChannelEnable(0)
            else:
                self.sn.device.setInputChannelEnable(label_value, 0)
        else:
            button.config(text="Enable", bg="green")
            if label == "Sync":
                self.sn.device.setSyncChannelEnable(0)
            else:
                self.sn.device.setInputChannelEnable(label_value, 1)

    def toggle_start(self, button, tab):
        if button["text"] == "Start":
            button.config(text="Running", bg="red")
            threading.Thread(target=self.start_measurement, args=(tab,), daemon=True).start()
        else:
            button.config(text='Start', bg='green')
            self.stop_measurement(tab)

    def start_measurement(self, tab):
        if tab == "time_trace":
            self.time_trace_running = True
            bin_width = int(self.entries["tt_bin_width"].get())
            window_size = float(self.entries["tt_window_size"].get())
            acquisition_time = int(self.entries["tt_acquisition_time"].get())

            self.sn.timeTrace.clearMeasure()
            self.sn.timeTrace.setNumBins(bin_width)
            self.sn.timeTrace.setHistorySize(window_size)
            self.sn.timeTrace.measure(acquisition_time, waitFinished=False, savePTU=False)

            self.measure_time_trace()
        elif tab == "histogram":
            self.measure_histogram()
        elif tab == "correlation":
            self.measure_correlation()
    
    def stop_measurement(self, tab):
        # Stop the measurement by setting the stop flag
        self.stop_flag = True
        if tab == "time_trace":
            self.time_trace_running = False
            self.sn.timeTrace.stopMeasure()
            self.sn.timeTrace.clearMeasure()
        elif tab == "histogram":
            self.sn.histogram.stopMeasure()
            self.sn.histogram.clearMeasure()
        elif tab == "correlation":
            self.sn.correlation.stopMeasure()   
            self.sn.correlation.clearMeasure()           
    
    def measure_time_trace(self):
        counts, times = self.sn.timeTrace.getData()

        self.ax_time_trace.clear()
        line, = self.ax_time_trace.plot([], [], label="Time Trace")

        # Set labels and title
        self.ax_time_trace.set_xlabel("Time (s)", fontsize=18, fontname='Arial')
        self.ax_time_trace.set_ylabel("Photon Count Rate (Cnt/s)", fontsize=18, fontname='Arial')
        self.ax_time_trace.set_title("Time Trace", fontsize=18, fontname='Arial')
        self.ax_time_trace.tick_params(axis='both', which='major', labelsize=18)

        while self.time_trace_running:
            finished = self.sn.timeTrace.isFinished()
            counts, times = self.sn.timeTrace.getData()
            print("still in measure_time_trace")

            line.set_data(times, counts[1])
            self.ax_time_trace.relim()
            self.ax_time_trace.autoscale_view()
            self.canvas_time_trace.draw()

            # Update the canvas
            self.canvas_time_trace.draw()
            time.sleep(0.1)            
            if finished or not self.time_trace_running:
                self.time_trace_button.config(text="Start", bg="green")
                break

        print("out of measure_time_trace")
        
    def measure_histogram(self):
        self.stop_flag = False
        for i in range(100):  # Simulating 100 data points
            if self.stop_flag:
                break
            self.data["histogram"].append(random.random())
            self.update_plot("histogram")
            time.sleep(0.1)
    
    def measure_correlation(self):
        self.stop_flag = False
        for i in range(100):  # Simulating 100 data points
            if self.stop_flag:
                break
            self.data["correlation"].append(random.random())
            self.update_plot("correlation")
            time.sleep(0.1)
    
    def update_plot(self, tab):
        if tab == "time_trace":   
            self.update_time_trace()
            self.root.after(10, self.measure_time_trace)  # Update every 10 ms
        elif tab == "histogram":
            self.ax_histogram.clear()
            self.ax_histogram.hist(self.data["histogram"], bins=20)
            self.canvas_histogram.draw()
        elif tab == "correlation":
            self.ax_correlation.clear()
            self.ax_correlation.plot(self.data["correlation"])
            self.canvas_correlation.draw()
    
    def save_data(self, tab):
        if tab == "time_trace":
            filename = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("TXT files", "*.txt")])
            if filename:
                with open(filename, 'w', newline='') as file:
                    writer = csv.writer(file, delimiter='\t')
                    counts, times = self.sn.timeTrace.getData()
                    writer.writerows(np.column_stack((times, counts[1])))
        elif tab == "histogram":
            filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if filename:
                with open(filename, 'w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(["Histogram Data"])
                    writer.writerows([[x] for x in self.data["histogram"]])
                messagebox.showinfo("Save Data", "Data saved successfully!")
        elif tab == "correlation":
            filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if filename:
                with open(filename, 'w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(["Correlation Data"])
                    writer.writerows([[x] for x in self.data["correlation"]])
                messagebox.showinfo("Save Data", "Data saved successfully!")

if __name__ == "__main__":
    root = tk.Tk()
    app = MeasurementApp(root)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
