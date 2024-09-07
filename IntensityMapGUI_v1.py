import tkinter as tk
from tkinter import font as tkFont
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import struct
import socket
import threading
import time

def on_closing():
    # Close the server connections when the window is closed
    #if app.client_socket1:
    #    app.client_socket1.close()
    #if app.client_socket2:
    #    app.client_socket2.close()
    
    plt.close('all')  # Close all matplotlib plots
    root.destroy()

class IntensityMapGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Fluorescence Scanning")
        self.root.geometry("1280x1024")

        self.move_x = 0
        self.move_y = 0
        self.acq_time = 100
        self.step = 2
        self.frame = 10
        self.count_rate = 0

        self.is_running = False
        self.client1_thread = None
        self.client2_thread = None
        self.client1_running = False
        self.client2_running = False
        self.client_socket1 = None
        self.client_socket2 = None

        self.setup_fonts()
        self.setup_variables()
        self.setup_plot()
        self.setup_controls()
        self.setup_bindings()

    def setup_fonts(self):
        self.arr18 = tkFont.Font(family='Arial', size=18)

    def setup_variables(self):
        self.is_running = False
        self.cursor_x = tk.IntVar(value=0)
        self.cursor_y = tk.IntVar(value=0)
        self.intensity = tk.DoubleVar(value=0.0)
        self.move_x = tk.IntVar(value=0)
        self.move_y = tk.IntVar(value=0)
        self.acq_time = tk.IntVar(value=100)
        self.step = tk.IntVar(value=2)
        self.frame = tk.IntVar(value=10)

        # Variables for server IPs and Ports
        self.server1_ip = tk.StringVar(value="127.0.0.1")
        self.server1_port = tk.IntVar(value=12345)
        self.server2_ip = tk.StringVar(value="127.0.0.1")
        self.server2_port = tk.IntVar(value=65053)

    def setup_plot(self):
        self.fig, self.ax = plt.subplots(figsize=(5, 5))

        self.default_intensity = np.zeros((int(self.frame.get()), int(self.frame.get())))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.im = self.ax.imshow(self.default_intensity, cmap='hot')
        self.fig.colorbar(self.im)
        self.canvas.draw()
        self.crosshair, = self.ax.plot([], [], color='blue', marker='+', markeredgewidth=5, markersize=20)

    def setup_controls(self):
        self.start_button = tk.Button(self.root, text="Start", bg="green", font=self.arr18, command=self.toggle_plotting)
        self.start_button.pack(side=tk.TOP, pady=10)
        self.setup_status_panel()
        self.setup_input_panel()
        self.setup_server_inputs()
        self.setup_z_buttons()

    def setup_status_panel(self):
        status_frame = tk.Frame(self.root)
        status_frame.pack(side=tk.TOP, pady=10)
        tk.Label(status_frame, text="X:", font=self.arr18).pack(side=tk.LEFT)
        self.x_label = tk.Label(status_frame, textvariable=self.cursor_x, font=self.arr18)
        self.x_label.pack(side=tk.LEFT, padx=5)

        tk.Label(status_frame, text="Y:", font=self.arr18).pack(side=tk.LEFT)
        self.y_label = tk.Label(status_frame, textvariable=self.cursor_y, font=self.arr18)
        self.y_label.pack(side=tk.LEFT, padx=5)

        tk.Label(status_frame, text="Counts Rate:", font=self.arr18).pack(side=tk.LEFT)
        self.counts_label = tk.Label(status_frame, textvariable=self.intensity, font=self.arr18)
        self.counts_label.pack(side=tk.LEFT, padx=5)

    def setup_input_panel(self):
        input_frame = tk.Frame(self.root)
        input_frame.pack(side=tk.TOP, pady=10)
        self.create_input(input_frame, "Move X:", self.move_x)
        self.create_input(input_frame, "Move Y:", self.move_y)
        self.create_input(input_frame, "Acquisition Time (ms):", self.acq_time)
        self.create_input(input_frame, "Step Size:", self.step)
        self.create_input(input_frame, "Frame Size:", self.frame)

    def create_input(self, frame, label, var):
        tk.Label(frame, text=label, font=self.arr18).pack(side=tk.LEFT)
        entry = tk.Entry(frame, textvariable=var, font=self.arr18, width=5)
        entry.pack(side=tk.LEFT, padx=5)

    def setup_server_inputs(self):
        server_frame = tk.Frame(self.root)
        server_frame.pack(side=tk.TOP, pady=10)

        # Server 1 IP and Port inputs
        tk.Label(server_frame, text="Nanonis IP:", font=self.arr18).pack(side=tk.LEFT)
        server1_ip_entry = tk.Entry(server_frame, textvariable=self.server1_ip, font=self.arr18, width=12)
        server1_ip_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(server_frame, text="Port:", font=self.arr18).pack(side=tk.LEFT)
        server1_port_entry = tk.Entry(server_frame, textvariable=self.server1_port, font=self.arr18, width=6)
        server1_port_entry.pack(side=tk.LEFT, padx=5)

        # Server 2 IP and Port inputs
        tk.Label(server_frame, text="Picoquant IP:", font=self.arr18).pack(side=tk.LEFT, padx=10)
        server2_ip_entry = tk.Entry(server_frame, textvariable=self.server2_ip, font=self.arr18, width=12)
        server2_ip_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(server_frame, text="Port:", font=self.arr18).pack(side=tk.LEFT)
        server2_port_entry = tk.Entry(server_frame, textvariable=self.server2_port, font=self.arr18, width=6)
        server2_port_entry.pack(side=tk.LEFT, padx=5)

    def setup_z_buttons(self):
        z_button_frame = tk.Frame(self.root)
        z_button_frame.pack(side=tk.TOP, pady=10)
        self.z_plus_button = tk.Button(z_button_frame, text="Z+", font=self.arr18, command=lambda: self.flash_button(self.z_plus_button))
        self.z_plus_button.pack(side=tk.LEFT, padx=5)

        self.z_minus_button = tk.Button(z_button_frame, text="Z-", font=self.arr18, command=lambda: self.flash_button(self.z_minus_button))
        self.z_minus_button.pack(side=tk.LEFT, padx=5)

    def setup_bindings(self):
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.canvas.mpl_connect("motion_notify_event", self.on_drag)

    def toggle_plotting(self):
        if not self.client1_running and not self.client2_running:
            # Start client 1
            self.client1_thread = threading.Thread(target=self.tcp_client1, daemon=True)
            self.client1_thread.start()
            self.client1_running = True
            
            # Start client 2
            self.client2_thread = threading.Thread(target=self.tcp_client2, args=(0, 0), daemon=True)
            self.client2_thread.start()
            self.client2_running = True

            self.start_button.config(text="Running", font=self.arr18, bg="red")
            self.is_running = True  # Data sending should now be active
        else:
            # Toggle between Start/Stop without reconnecting the servers
            self.client1_running = False
            self.client2_running = False
            self.is_running = not self.is_running

            # Update the button label depending on the current state
            self.start_button.config(text="Start", font=self.arr18, bg="green")
        
        # TCP client 1 function
    def tcp_client1(self):
        cnt = 0
        frame = int(self.frame.get())
        acq_time = int(self.acq_time.get()) / 1000  # Convert ms to seconds
    
        try:
            if not self.client_socket1:
                self.client_socket1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket1.connect((self.server1_ip.get(), int(self.server1_port.get())))
                #print("Connected to Nanonis TCP/IP")

            while self.client1_running:
                #print("tcp_client1 is running")
                if self.is_running:
                    for y in range(int(self.frame.get())):
                        if not self.client1_running:
                            break
                        self.client_socket1.sendall(b'StartMoveY-')
                        if y % 2 == 0:
                            x_range = range(frame)  # Left to Right
                        else:
                            x_range = range(frame-1, -1, -1)  # Right to Left (Zig-Zag)

                        for x in x_range:
                            if not self.client1_running:
                                break                            
                            self.cursor_x.set(x)
                            self.cursor_y.set(y)
                            
                            if y % 2 == 0:
                                self.client_socket1.sendall(b'StartMoveX+')  # Left to Right
                            else:
                                self.client_socket1.sendall(b'StartMoveX-')  # Right to Left (Zig-Zag)
                            # After sending X,Y data, trigger tcp_client2
                            time.sleep(acq_time)
                            client2_thread = threading.Thread(target=self.tcp_client2, args=(x, y), daemon=True)
                            client2_thread.start()
                        
                        cnt = cnt + 1
                        if cnt == frame:
                            cnt = 0
                            #self.send_stop_to_server2()
                            self.start_button.config(text="Start", font=self.arr18, bg="green")
                            self.client1_running = False
                            self.client2_running = False
        except Exception as e:
            print(f"Client 1 error: {e}")

    # TCP client 2 function
    def tcp_client2(self, x, y):
        try:
            # Establish the connection only once
            if not self.client_socket2:
                self.client_socket2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket2.connect((self.server2_ip.get(), int(self.server2_port.get())))
                #print("Connected to Picoquant TCP/IP")

            # Send data only if running
            if self.client2_running:
                self.client_socket2.sendall(b'Start')
                data = b''
                while len(data) < 4:
                    packet = self.client_socket2.recv(4 - len(data))
                    if not packet:
                        raise ConnectionError("Socket connection broken")
                    data += packet

                # Unpack the received data (intensity value)
                intensity_value = struct.unpack('!I', data)[0]

                # Update the plot with the received intensity value for the given (x, y)
                self.update_plot(x, y, intensity_value)

        except Exception as e:
            print(f"Client 2 error: {e}")
            
    def send_stop_to_server2(self):
        try:
            if self.client_socket2:
                # Send "Stop" message to server2
                self.client_socket2.sendall(b'Stop')
                #print("Sent 'Stop' to server2")
        except Exception as e:
            print(f"Error sending 'Stop' to server2: {e}")
        
    def update_plot(self, x, y, intensity_value):
        if self.is_running:
            frame_size = int(self.frame.get())
            
            if self.im.get_array().shape != (frame_size, frame_size):
                new_intensity_data = np.zeros((frame_size, frame_size))
                old_intensity_data = self.im.get_array()

                # Copy the values from the old array into the new one
                min_size = min(old_intensity_data.shape[0], frame_size)
                new_intensity_data[:min_size, :min_size] = old_intensity_data[:min_size, :min_size]

                # Update the image data
                self.im.set_data(new_intensity_data)
            
            intensity_data = self.im.get_array()
            intensity_data[y, x] = intensity_value
            self.im.set_data(intensity_data)
            self.im.set_clim(vmin=np.min(intensity_data), vmax=np.max(intensity_data))
            self.canvas.draw()
            #self.root.after(500, self.update_plot)

    def on_click(self, event):
        if event.inaxes:
            # Get the current frame size (i.e., resolution)
            frame_size = self.im.get_array().shape[0]

            # Clamp the coordinates within valid bounds
            x = int(min(max(event.xdata, 0), frame_size - 1))
            y = int(min(max(event.ydata, 0), frame_size - 1))

            # Update the crosshair and the cursor positions safely
            self.update_crosshair(x, y)

    def on_drag(self, event):
        if event.inaxes and event.button == 1:  # Left click drag
            # Get the current frame size (i.e., resolution)
            frame_size = self.im.get_array().shape[0]

            # Clamp the coordinates within valid bounds
            x = int(min(max(event.xdata, 0), frame_size - 1))
            y = int(min(max(event.ydata, 0), frame_size - 1))

            # Update the crosshair and the cursor positions safely
            self.update_crosshair(x, y)

    def update_crosshair(self, x, y):
        # Set the crosshair position to the clamped coordinates
        self.crosshair.set_data([x], [y])

        # Update cursor x, y, and intensity values
        self.cursor_x.set(x)
        self.cursor_y.set(y)
        self.intensity.set(self.im.get_array()[y, x])

        # Redraw the canvas with updated crosshair
        self.canvas.draw()

    def flash_button(self, button):
        button.config(bg="yellow")
        self.root.after(100, lambda: button.config(bg=self.root.cget('bg')))

if __name__ == "__main__":
    root = tk.Tk()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    app = IntensityMapGUI(root)
    root.mainloop()
