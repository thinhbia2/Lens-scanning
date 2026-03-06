import tkinter as tk
from tkinter import font as tkFont
from tkinter import ttk, filedialog, messagebox
import numpy as np
import math
from e70d2s import e70
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from fitting_methods import twoDfittings
from matplotlib.colors import Normalize
from thorlabs_control import KDC101Controller
from stepper_motor_NP import NDFilterGUI
import matplotlib.gridspec as gridspec
import numbers 
import mplcursors
import struct
import socket
import serial
import threading
import clr
import os
import time
import csv

def on_closing():
    plt.close('all')  # Close all matplotlib plots
    root.destroy()

class IntensityMapGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Fluorescence Scanning")
        self.root.geometry("1500x1024")

        self.center_x = 20
        self.center_y = 20
        self.acq_time = 50
        self.pixel = 50
        self.frame = 10
        self.count_rate = 0

        self.running_pol = False
        self.is_running = False 
        self.running_thread = None

        self.prm1 = KDC101Controller()
        self.thorlabs_connected = None
        self.thorlabs_running = False
        self.thorlabs_thread = None

        self.e70d2s = None
        self.e70d2s_thread = None
        self.e70d2s_connected = False

        self.sock = None
        self.picoharp_connected = False

        self.setup_fonts()
        self.setup_variables()
        #self.setup_plot()

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(expand=1, fill="both")
        self.style = ttk.Style()
        self.style.configure('TCombobox', font=self.arr18)
        self.style.configure('TNotebook.Tab', font=self.arr18)
        self.style.map('TNotebook.Tab',
                       background=[('selected', 'red')],
                       foreground=[('selected', 'blue')],
                       relief=[('selected', 'flat')])

        # Tab 1 - Main Scanning tab
        self.scan_tab = tk.Frame(self.tabs)
        self.tabs.add(self.scan_tab, text="Scan")

        # Tab 2 - Polarization tab
        self.polarization_tab = tk.Frame(self.tabs)
        self.tabs.add(self.polarization_tab, text="Polarization")

        # Tab 2 - ND Filter tab
        self.ndfilter_tab = tk.Frame(self.tabs)
        self.tabs.add(self.ndfilter_tab, text="NDFilter")

        # Build tabs
        self.create_scan_tab()
        self.create_polarization_tab()
        self.stepper_motor = NDFilterGUI(self.ndfilter_tab)

    def setup_fonts(self):
        self.arr18 = tkFont.Font(family='Arial', size=18)

    def setup_variables(self):
        self.is_running = False
        self.scan_mode = tk.StringVar(value="Forward")
        self.index_x = -1
        self.index_y = -1
        self.current_x = tk.StringVar(value="0")
        self.current_y = tk.StringVar(value="0")
        self.intensity1 = tk.StringVar(value="0.0")
        self.center_x = tk.StringVar(value="20")
        self.center_y = tk.StringVar(value="20")
        self.rotation = tk.StringVar(value="0")
        self.acq_time = tk.IntVar(value=50)
        self.pixel = tk.IntVar(value=10)
        self.frame = tk.StringVar(value="20")

        self.speed = tk.StringVar(value="10.0")
        self.accel = tk.StringVar(value="10.0")
        self.step_pol = tk.StringVar(value="5.0")
        self.acq_time_pol = tk.IntVar(value=100)
        self.cur_angle = tk.StringVar(value="0.0")
        self.goto_angle_var = tk.StringVar(value="0.0")
        self.angles_pol = []
        self.intensities_pol = []
        self.norm_intensities_pol = []
        self.norm2_intensities_pol = []

        self.vmin1 = tk.DoubleVar(value=0.0)
        self.vmax1 = tk.DoubleVar(value=1.0)

        self.min1 = 0
        self.max1 = 0
        self.color_scale = 0.25
        self.tol=5e-4

        # Track the active colorbar and dragging state
        self.manual_colorbar1 = False
        self.active_colorbar = None
        self.dragging = False  # Track whether a drag is in progress
        self.dragging_vmin = False  # Track if dragging affects vmin
        self.dragging_vmax = False  # Track if dragging affects vmax
        self.last_y = None  # Stores last y-position to detect dragging direction

        # Define available colormaps
        self.colormap_options = ["afmhot", "hot", "viridis", "plasma", "inferno", "magma", "cividis"]
        self.fitting_options = ["Raw", "Subtract Average", "Subtract Slope", "Subtract Linear Fit", "Subtract Parabolic Fit"]
        self.colormap1 = tk.StringVar(value=self.colormap_options[1])  # Default colormap
        self.fitting1 = tk.StringVar(value=self.fitting_options[0])

        self.fitting_methods = {
            "Raw": twoDfittings.raw,
            "Subtract Average": twoDfittings.subtract_average,
            "Subtract Slope": twoDfittings.subtract_slope,
            "Subtract Linear Fit": twoDfittings.subtract_linear_fit,
            "Subtract Parabolic Fit": twoDfittings.subtract_parabolic_fit
        }

        # Variables for server IPs and Ports
        self.e70d2s_address = tk.StringVar(value="01")
        self.e70d2s_port = tk.StringVar(value="COM1")
        self.picoharp_ip = tk.StringVar(value="192.168.236.2")
        self.picoharp_port = tk.IntVar(value=65053)

    def create_scan_tab(self):
        self.setup_connection()
        self.setup_plot()
        self.setup_controls()

    def setup_connection(self):        
        connection_frame = tk.Frame(self.scan_tab)
        connection_frame.pack(side=tk.TOP, pady=5)

        # E70.D2S COM port inputs
        tk.Label(connection_frame, text="E70.D2S Add", font=self.arr18).pack(side=tk.LEFT)
        e70d2s_address_entry = tk.Entry(connection_frame, textvariable=self.e70d2s_address, font=self.arr18, width=3)
        e70d2s_address_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(connection_frame, text="Port", font=self.arr18).pack(side=tk.LEFT)
        self.e70d2s_port_combobox = ttk.Combobox(connection_frame, textvariable=self.e70d2s_port, font=self.arr18, width=6)
        self.e70d2s_port_combobox.pack(side=tk.LEFT, padx=5)
        self.e70d2s_port_combobox.bind("<Button-1>", self.update_ports(self.e70d2s_port_combobox, self.e70d2s_port))

        self.e70d2s_button = tk.Button(connection_frame, text="Connect", bg="red", font=self.arr18, command=self.e70d2s_connect)
        self.e70d2s_button.pack(side=tk.LEFT, padx=5)

        # Picoharp Server IP and Port inputs
        tk.Label(connection_frame, text="Picoquant IP", font=self.arr18, padx=5).pack(side=tk.LEFT)
        picoharp_ip_entry = tk.Entry(connection_frame, textvariable=self.picoharp_ip, font=self.arr18, width=13)
        picoharp_ip_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(connection_frame, text="Port", font=self.arr18).pack(side=tk.LEFT)
        picoharp_port_entry = tk.Entry(connection_frame, textvariable=self.picoharp_port, font=self.arr18, width=6)
        picoharp_port_entry.pack(side=tk.LEFT, padx=5)

        self.picoharp_button = tk.Button(connection_frame, text="Connect", bg="red", font=self.arr18, command=self.picoharp_connect)
        self.picoharp_button.pack(side=tk.LEFT, padx=5)

    def update_ports(self, combobox, variable, event=None):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        combobox["values"] = ports    
        if ports and variable.get() not in ports:
            variable.set(ports[0])

    def setup_plot(self):
        self.fig, self.ax1 = plt.subplots(figsize=(6, 6))
        self.fig.subplots_adjust(left=-1.5, right=0.9, bottom=0.1, top=0.9)

        # Create the default intensity maps (initialized with zeros)
        self.raw_intensity1 = np.zeros((int(self.pixel.get()), int(self.pixel.get())))

        # First intensity map on the left
        self.im1 = self.ax1.imshow(self.raw_intensity1, cmap=self.colormap1.get(), 
                                   norm=Normalize(vmin=self.vmin1.get(), vmax=self.vmax1.get()))
        self.colorbar1 = self.fig.colorbar(self.im1, ax=self.ax1, fraction=0.046, pad=0.04)
        self.ax1.set_xticks([])
        self.ax1.set_yticks([])

        # Attach the canvas to the Tkinter window
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.scan_tab)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Crosshair markers for both intensity maps
        self.crosshair1, = self.ax1.plot([], [], color='blue', marker='+', markeredgewidth=5, markersize=20)

        # Initial draw of the canvas
        self.canvas.draw()
        
        # Bind the event handlers
        self.setup_bindings()
        self.setup_colorbar_interaction()

    def setup_colorbar_interaction(self):
        """Connects mouse events to enable interactive colorbar adjustments."""
        self.fig.canvas.mpl_connect("button_press_event", self.on_colorbar_click)
        self.fig.canvas.mpl_connect("motion_notify_event", self.on_colorbar_drag)
        self.fig.canvas.mpl_connect("button_release_event", self.on_colorbar_release)

    def on_colorbar_click(self, event):
        """Detects which colorbar was clicked and activates it for dragging."""
        if event.inaxes == self.colorbar1.ax:
            self.active_colorbar = "colorbar1"
        else:
            self.active_colorbar = None
            return

        self.dragging = True  # Start dragging
        self.last_y = event.ydata  # Store the initial y-position when clicked

        # Determine whether the user clicked in the top or bottom half
        if self.active_colorbar == "colorbar1":
            self.manual_colorbar1 = True
            vmin, vmax = self.vmin1.get(), self.vmax1.get()

        middle_value = (vmax + vmin) / 2

        # If clicked in the top half, drag affects vmax; otherwise, it affects vmin
        self.dragging_vmax = self.last_y > middle_value
        self.dragging_vmin = not self.dragging_vmax

    def on_colorbar_drag(self, event):
        """Adjusts vmin/vmax dynamically while dragging on the active colorbar."""
        if not self.dragging or self.active_colorbar is None or event.inaxes is None:
            return  # No active colorbar or not dragging

        # Stop dragging if the cursor leaves the colorbar
        if (self.active_colorbar == "colorbar1" and event.inaxes != self.colorbar1.ax):
            self.dragging = False  # Stop dragging when outside the colorbar
            return

        # Select correct vmin/vmax, image, and colorbar
        if self.active_colorbar == "colorbar1":
            vmin_var, vmax_var, img, colorbar = self.vmin1, self.vmax1, self.im1, self.colorbar1

        # Check if ydata is valid
        if event.ydata is None or self.last_y is None:
            return

        # Compute colorbar range
        step = 0.04 * (vmax_var.get() - vmin_var.get())  # Adjust step size dynamically

        # Determine dragging direction (Compare current y-position with last recorded y-position)
        if event.ydata > self.last_y:  # Mouse moved **up**
            if self.dragging_vmax:
                vmax_var.set(vmax_var.get() - step)  # Drag Up (Top Half) → vmax Decreases
            elif self.dragging_vmin:
                vmin_var.set(vmin_var.get() - step)  # Drag Up (Bottom Half) → vmin Decreases
        elif event.ydata < self.last_y:  # Mouse moved **down**
            if self.dragging_vmax:
                vmax_var.set(vmax_var.get() + step)  # Drag Down (Top Half) → vmax Increases
            elif self.dragging_vmin:
                vmin_var.set(vmin_var.get() + step)  # Drag Down (Bottom Half) → vmin Increases

        img.set_clim(vmin=vmin_var.get(), vmax=vmax_var.get())
        # Apply updates
        if self.active_colorbar == "colorbar1":
            self.colorbar1.update_normal(self.im1)
        self.canvas.draw_idle()
        #self.fig.canvas.flush_events()

    def on_colorbar_release(self, event):
        """Stops dragging when the mouse button is released."""
        self.dragging = False
        self.dragging_vmin = False
        self.dragging_vmax = False
        self.active_colorbar = None  # Reset active colorbar when releasing click
        self.last_y = None  # Reset last y-position

    def setup_controls(self):
        controls_frame = tk.Frame(self.scan_tab)
        controls_frame.pack(side=tk.TOP, pady=10)

        self.setup_status_colorbar_panel(controls_frame)
        self.setup_input_panel()
        
        button_frame = tk.Frame(self.scan_tab)
        button_frame.pack(side=tk.TOP, expand=True)  # This will allow the button to be centered

        self.start_button = tk.Button(button_frame, text="Start", bg="green", font=self.arr18, command=self.start_pause)
        self.start_button.pack(side=tk.LEFT, pady=0)
        self.save_button = tk.Button(button_frame, text="Save Data", bg="blue", font=self.arr18, command=self.save_intensity_maps)
        self.save_button.pack(side=tk.LEFT, padx=10, pady=0)

        #self.setup_bindings()

    def setup_status_colorbar_panel(self, parent_frame):
        # Status frame for Height
        status_colorbar_frame = tk.Frame(parent_frame)
        status_colorbar_frame.pack(side=tk.LEFT, padx=2)
        
        tk.Label(status_colorbar_frame, text="X (µm):", font=self.arr18).pack(side=tk.LEFT)
        self.x_label = tk.Label(status_colorbar_frame, textvariable=self.current_x, font=self.arr18, width=6)
        self.x_label.pack(side=tk.LEFT, padx=2)

        tk.Label(status_colorbar_frame, text="Y (µm):", font=self.arr18).pack(side=tk.LEFT)
        self.y_label = tk.Label(status_colorbar_frame, textvariable=self.current_y, font=self.arr18, width=6)
        self.y_label.pack(side=tk.LEFT, padx=2)

        tk.Label(status_colorbar_frame, text="Photon Rate (Hz):", font=self.arr18).pack(side=tk.LEFT)
        self.photon_label = tk.Label(status_colorbar_frame, textvariable=self.intensity1, font=self.arr18, width=6)
        self.photon_label.pack(side=tk.LEFT, padx=2)

        tk.Label(status_colorbar_frame, text="Palette", font=self.arr18).pack(side=tk.LEFT, padx=2)
        self.colormap1_combo = ttk.Combobox(status_colorbar_frame, textvariable=self.colormap1, font=self.arr18, width=6, values=self.colormap_options, state="readonly")
        self.colormap1_combo.pack(side=tk.LEFT, padx=2)
        self.colormap1_combo.bind("<<ComboboxSelected>>", lambda e: self.update_colormap(1))

        tk.Label(status_colorbar_frame, text="Processing", font=self.arr18).pack(side=tk.LEFT, padx=2)
        self.fitting1_combo = ttk.Combobox(status_colorbar_frame, textvariable=self.fitting1, font=self.arr18, width=18, values=self.fitting_options, state="readonly")
        self.fitting1_combo.pack(side=tk.LEFT, padx=2)
        self.fitting1_combo.bind("<<ComboboxSelected>>", lambda e: self.update_fitting1())
   
    def update_colormap(self, plot_number):
        """Updates the colormap for the selected plot."""
        if plot_number == 1:
            self.im1.set_cmap(self.colormap1.get())

        self.canvas.draw_idle()  # Redraw with the new colormap

    def update_fitting1(self):
        fitted_data1 = self.fitting_methods.get(self.fitting1.get(), twoDfittings.raw)(self.raw_intensity1)
        vmin = np.min(fitted_data1)
        vmax = np.max(fitted_data1)
        diff = 0.5*(vmax - vmin)
        self.im1.set_data(fitted_data1)
        self.im1.set_clim(vmin=vmin-diff, vmax=vmax+diff)
        self.vmin1.set(vmin-diff)
        self.vmax1.set(vmax+diff)
        self.canvas.draw()

    def setup_input_panel(self):
        input_frame = tk.Frame(self.scan_tab)
        input_frame.pack(side=tk.TOP, pady=5)
        self.create_input(input_frame, "Center X (µm)", self.center_x, 7)
        self.create_input(input_frame, "Center Y (µm)", self.center_y, 7)
        self.create_input(input_frame, "Rotation (°)", self.rotation, 5)
        self.create_input(input_frame, "Acq Time (ms)", self.acq_time, 4)
        self.create_input(input_frame, "Pixels", self.pixel, 3)
        self.create_input(input_frame, "Frame Size (µm)", self.frame, 3)
        tk.Label(input_frame, text="Raster", font=self.arr18).pack(side=tk.LEFT)
        combobox = ttk.Combobox(input_frame, textvariable=self.scan_mode, state="readonly", font=self.arr18, width=7)
        combobox['values'] = ("Forward", "Backward", "Bidirectional", "Zigzag")  # Set the options in the dropdown
        combobox.current(1)
        combobox.pack(side=tk.LEFT, padx=2)

    def create_input(self, frame, label, var, width):
        tk.Label(frame, text=label, font=self.arr18).pack(side=tk.LEFT)
        entry = tk.Entry(frame, textvariable=var, font=self.arr18, width=width)
        entry.pack(side=tk.LEFT, padx=5)

    def create_polarization_tab(self):
        self.polarization_frame = tk.Frame(self.polarization_tab)
        self.polarization_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        self.connect_btn = tk.Button(self.polarization_frame, text="Connect", bg="red", font=self.arr18, command=self.deivce_connect)
        self.connect_btn.grid(row=0, column=4, pady=5)

        tk.Label(self.polarization_frame, text="Speed (°/s)", font=self.arr18).grid(row=1, column=0)
        self.speed_entry = tk.Entry(self.polarization_frame, textvariable=self.speed, font=self.arr18, width=6)
        self.speed_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(self.polarization_frame, text="Accel (°/s²)", font=self.arr18).grid(row=1, column=2)
        self.accel_entry = tk.Entry(self.polarization_frame, textvariable=self.accel, font=self.arr18, width=6)
        self.accel_entry.grid(row=1, column=3, padx=5, pady=5)

        tk.Label(self.polarization_frame, text="Step (°)", font=self.arr18).grid(row=1, column=4)
        self.step_entry = tk.Entry(self.polarization_frame, textvariable=self.step_pol, font=self.arr18, width=6)
        self.step_entry.grid(row=1, column=5, padx=5, pady=5)

        tk.Label(self.polarization_frame, text="Acq Time (ms)", font=self.arr18).grid(row=1, column=6)
        self.acq_entry = tk.Entry(self.polarization_frame, textvariable=self.acq_time_pol, font=self.arr18, width=6)
        self.acq_entry.grid(row=1, column=7, padx=5, pady=5)

        # Label and Entry for target angle
        self.goto_frame = tk.Frame(self.polarization_frame)
        self.goto_frame.grid(row=2, column=0, columnspan=8, pady=5, sticky="w")

        tk.Label(self.goto_frame, text="Go To (°)", font=self.arr18).grid(row=0, column=0, padx=5)
        self.goto_angle_entry = tk.Entry(self.goto_frame, textvariable=self.goto_angle_var, font=self.arr18, width=6)
        self.goto_angle_entry.grid(row=0, column=1, padx=5)

        # Button to trigger move
        self.goto_btn = tk.Button(self.goto_frame, text="Move", font=self.arr18, bg="orange", command=self.goto_angle)
        self.goto_btn.grid(row=0, column=2, padx=5)
        self.goto_btn.config(state='disabled')

        self.start_btn = tk.Button(self.polarization_frame, text="Start", bg="green", font=self.arr18, command=self.toggle_measurement_pol)
        self.start_btn.grid(row=2, column=4, pady=5)
        self.start_btn.config(state='disabled')

        tk.Label(self.polarization_frame, text="Angle (°):", font=self.arr18).grid(row=3, column=2)
        self.angle_label = tk.Label(self.polarization_frame, textvariable=self.cur_angle, font=self.arr18)
        self.angle_label.grid(row=3, column=3, padx=5, pady=5)

        tk.Label(self.polarization_frame, text="Cnt rate (Hz):", font=self.arr18).grid(row=3, column=4)
        self.photon_label = tk.Label(self.polarization_frame, textvariable=self.intensity1, font=self.arr18)
        self.photon_label.grid(row=3, column=5, padx=5, pady=5)
        
        self.setup_plot_pol()

        # Save button
        self.pol_save = tk.Button(self.polarization_frame, text="Save Data", bg="blue", fg="white", font=self.arr18, command=self.save_data_pol)
        self.pol_save.grid(row=5, column=4, columnspan=1, pady=5)

    def goto_angle(self):
        try:
            self.prm1.set_motion_params(float(self.speed.get()),float(self.accel.get()))
            angle_str = self.goto_angle_var.get().replace(',', '.')
            target_angle = float(angle_str)
            self.goto_btn.config(text="Moving", state="disabled")
            self.goto_btn.update()
            self.start_btn.config(state='disabled')
            self.start_btn.update()
            self.prm1.move_to(target_angle)
            current_angle = self.prm1.get_position()
            self.cur_angle.set(f"{current_angle:.2f}")
        except ValueError:    
            print("Invalid angle input.")
        finally:
            # Restore button after move
            self.goto_btn.config(text="Move", state="normal")
            self.goto_btn.update()
            self.start_btn.config(state='normal')
            self.start_btn.update()

    def setup_plot_pol(self):
        self.fig, self.ax = plt.subplots(subplot_kw={'projection': 'polar'},figsize=(7, 7))
        self.canvas_pol = FigureCanvasTkAgg(self.fig, master=self.polarization_frame)
        self.canvas_pol.get_tk_widget().grid(row=4, column=1, columnspan=6)

    def update_plot(self):
        self.ax.clear()
        if not self.intensities_pol:
            return  # No data yet

        raw_intensity = np.array(self.intensities_pol)

        # Avoid division by zero if all values are the same
        range_val = raw_intensity.max() - raw_intensity.min()
        if range_val == 0:
            self.norm_intensities_pol  = np.ones_like(raw_intensity)
        else:
            self.norm_intensities_pol  = (raw_intensity - raw_intensity.min()) / range_val
        self.norm2_intensities_pol = raw_intensity / raw_intensity.max().tolist()
        self.ax.plot(self.angles_pol, self.norm_intensities_pol, marker='o', color='cornflowerblue', label=r'$\mathrm{(I - I_{min}) / (I_{max} - I_{min})}$')
        self.ax.plot(self.angles_pol, self.norm2_intensities_pol, marker='x', color='tomato', label=r'$\mathrm{I / I_{max}}$')
        self.ax.tick_params(labelsize=14)
        self.ax.set_title("Normalized Polarization", fontsize=18, fontname="Arial", pad=20)
        self.ax.set_yticklabels([]) 
        self.ax.legend(loc='upper right', fontsize=11, frameon=False, bbox_to_anchor=(1.16, 1.1))
        self.canvas_pol.draw()

    def toggle_measurement_pol(self):
        if not self.running_pol:
            self.running_pol = True
            self.picoharp_connected = True
            self.thorlabs_running = True
            self.thorlabs_thread = threading.Thread(target=self.measurement_pol, daemon=True)
            self.thorlabs_thread.start()
            self.start_btn.config(text="Running", font=self.arr18, bg="red")
            self.goto_btn.config(state="disabled")
        else:
            self.stop_measurement_pol()

    def measurement_pol(self):
        step = float(self.step_entry.get())
        acq_time = int(self.acq_entry.get())/1000

        self.angles_pol = []
        self.intensities_pol = []
        self.norm_intensities_pol = []
        self.norm2_intensities_pol = []
        self.ax.clear()
        self.canvas_pol.draw()

        current_angle = self.prm1.get_position()
        end_angle = current_angle + 360  # You can customize total rotation
        self.send_start_to_picoharp(int(self.acq_time.get()))
        self.prm1.set_motion_params(float(self.speed.get()),float(self.accel.get()))
        time.sleep(1)
        while self.running_pol and current_angle <= end_angle:
            move_angle = current_angle % 360
            self.prm1.move_to(move_angle)
            self.cur_angle.set(f"{move_angle:.2f}")
            time.sleep(acq_time)

            intensity = self.tcp_client2(-1, -1)
            if isinstance(intensity, numbers.Number):
                self.angles_pol.append(np.radians(current_angle))
                self.intensities_pol.append(intensity)
                self.update_plot()
            else:
                print("End polarization measurement")
            current_angle += step
        self.stop_measurement_pol()
    
    def stop_measurement_pol(self):
        self.running_pol = False
        self.send_stop_to_picoharp()
        self.picoharp_connected = False
        self.thorlabs_running = False
        self.thorlabs_thread = False
        self.goto_btn.config(state="normal")
        self.start_btn.config(text="Start", font=self.arr18, bg="green")

    def deivce_connect(self):
        if not self.picoharp_connected and not self.thorlabs_connected:
            self.pia13.connect()
            self.prm1.connect()
            self.picoharp_connect()
            self.picoharp_connected = True
            self.thorlabs_connected = True
            self.connect_btn.config(text="Connected", font=self.arr18, bg="green")
            self.goto_btn.config(state="normal")
            self.start_btn.config(state='normal')
            current_angle = self.prm1.get_position()
            self.cur_angle.set(f"{current_angle:.2f}")
        else:
            self.prm1.disconnect()
            self.picoharp_connected = False
            self.thorlabs_connected = False
            self.connect_btn.config(text="Disconnected", font=self.arr18, bg="red")
            self.goto_btn.config(state="disabled")
            self.start_btn.config(state='disabled')

    def save_data_pol(self):
        filename = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("TXT files", "*.txt")])

        if not filename:
            return  # User canceled save

        if filename:
            if filename.endswith(".txt"):
                filename = filename[:-4]
            rows = zip(
                        [f"{np.degrees(a):.2f}" for a in self.angles_pol],
                        [f"{int(i)}" for i in self.intensities_pol],
                        [f"{n:.4f}" for n in self.norm_intensities_pol]
                        )
            with open(filename + "_polar_data.txt", 'w', newline='') as f:
                writer = csv.writer(f, delimiter='\t')
                writer.writerow(["Angle (°)", "Raw Intensity", "Normalized Intensity"])
                writer.writerows(rows)

            self.fig.savefig(filename + "_polar_plot.png", dpi=300, bbox_inches="tight", pad_inches=0.2)

    def save_intensity_maps(self):
        filename = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("TXT files", "*.txt")])

        if not filename:
            return  # User canceled save

        if filename:
            if filename.endswith(".txt"):
                filename = filename[:-4]

            # Save the second intensity map to a file
            with open(filename + '_photon.txt', 'w', newline='') as f3:
                writer3 = csv.writer(f3, delimiter='\t')
                writer3.writerows(np.flipud(self.raw_intensity1))
            with open(filename + '_processed_photon.txt', 'w', newline='') as f4:
                writer4 = csv.writer(f4, delimiter='\t')
                writer4.writerows(np.flipud(self.im1.get_array()))
            self.save_image(self.im1.get_array(), self.colormap1.get(), self.vmin1.get(), self.vmax1.get(), filename + "_photon.png")

    def save_image(self, data, cmap, vmin, vmax, output_filename):
        fig = plt.figure(figsize=(3.5+0.5, 3.5))

        spec = gridspec.GridSpec(1, 2, width_ratios=[3.5, 0.15], wspace=0)
        ax = fig.add_subplot(spec[0])
        cax = fig.add_subplot(spec[1])
        im = ax.imshow(np.flipud(data), cmap=cmap, vmin=vmin, vmax=vmax, aspect="equal")  # Keep square aspect
        cbar = fig.colorbar(im, cax=cax)
        #cbar.ax.tick_params(labelsize=20)  # Adjust tick label size
        #cax.set_box_aspect(ax.get_window_extent().height / cax.get_window_extent().height)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_frame_on(False)

        # Remove colorbar x-axis labels (keep it vertical)
        cax.set_xticks([])

        # Save the image
        plt.savefig(output_filename, dpi=300, bbox_inches="tight", pad_inches=0.2)
        plt.close()

    def setup_bindings(self):
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.canvas.mpl_connect("key_press_event", self.on_key)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)

    def start_pause(self):
        if self.e70d2s_connected:
            if not self.is_running:
                self.is_running = True  # Data sending should now be active
                self.start_button.config(text="Running", font=self.arr18, bg="red")
                self.running_thread = threading.Thread(target=self.run_mapping)
                self.running_thread.start()
            else:
                self.send_stop_to_picoharp()
                self.index_x = -1
                self.index_y = -1
                self.is_running = False
                self.start_button.config(text="Start", font=self.arr18, bg="green")

    def e70d2s_connect(self):
        if not self.e70d2s_connected:
            self.e70d2s = e70(self.e70d2s_address.get(), self.e70d2s_port.get())

            port = self.e70d2s.auto_connect()
            if port != "":
                self.e70d2s_port.set(port)
                self.e70d2s.initial()
                self.e70d2s_button.config(text="Connected", bg="green")    
                self.e70d2s_connected = True
        else:
            self.e70d2s_stop()

    def e70d2s_stop(self):
        self.e70d2s_thread_running = False
        self.e70d2s_connected = False
        self.e70d2s.disconnect()
        self.e70d2s_button.config(text="Disconnect", bg="red")

    def picoharp_connect(self):
        if not self.picoharp_connected:
            if self.picoharp_tcpip_connect():
                self.picoharp_connected = True
                self.picoharp_button.config(text="Connected", bg="green")
        else:
            self.picoharp_connected = False
            self.picoharp_button.config(text="Disconnect", bg="red")
    
    def picoharp_tcpip_connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2.0)
            self.sock.connect((self.picoharp_ip.get(), int(self.picoharp_port.get())))
            #print(f"Connected to {self.picoharp_ip.get()}:{self.picoharp_port.get()}")
            return True
        except socket.timeout:
            raise TimeoutError(f"Connection to {self.picoharp_ip.get()}:{self.picoharp_port.get()} timed out")
            self.sock = None
            return False
        except socket.error as e:
            raise ConnectionError(f"Failed to connect to {self.picoharp_ip.get()}:{self.picoharp_port.get()}: {e}")
            self.sock = None
            return False

    def run_mapping(self):
        center_x = self.parse_input(self.center_x.get())
        center_y = self.parse_input(self.center_y.get())
        rotation = self.parse_input(self.rotation.get())
        frame = self.parse_input(self.frame.get())
        pixel = int(self.pixel.get())
        acq_time = int(self.acq_time.get()) / 1000  # Convert ms to seconds
        move = False
        current_x = 0
        current_y = 0
        intensity = 0
        cur_x = 0
        cur_y = 0
        
        resolution = frame / pixel
        start_x = center_x - (frame / 2)  # Start from the left
        start_y = center_y + (frame / 2)  # Start from the top

        try:
            self.send_start_to_picoharp(int(self.acq_time.get()))
            time.sleep(1.5)
            self.manual_colorbar1 = False
            #print("Scan Loop")
            while self.is_running:
                if not self.is_running:
                    break
                if self.is_running:
                    for y in range(pixel):
                        if not self.is_running:
                            break
                        current_y = start_y - y * resolution  # Move downward     

                        if self.scan_mode.get() == "Forward":
                            x_range = range(pixel)  # only L -> R
                        elif self.scan_mode.get() == "Backward":
                            x_range = range(pixel - 1, -1, -1)  # only R -> L

                        elif self.scan_mode.get() == "Bidirectional":
                            x_range = range(pixel)
                            x_rangeb = range(pixel - 1, -1, -1)
                            #x_range = range(pixel),                    # forward
                            #    range(pixel - 1, -1, -1)          # backward

                        elif self.scan_mode.get() == "Zigzag":
                            if y % 2 == 0:
                                x_range = range(pixel)       # forward
                            else:
                                x_range = range(pixel - 1, -1, -1)  # backward

                        else:
                            raise ValueError("Unknown scan mode")
                        for x in x_range:
                            if not self.is_running:
                               #print("Client 1 detected stop signal in x.")
                                break
                            current_x = start_x + x * resolution
                            cur_x, cur_y = self.rotate_point(current_x, current_y, center_x, center_y, rotation*(-1))
                            #print(f"x: {x}, y: {y}")
                            self.e70d2s.move_to(target_x=cur_x, target_y=cur_y, step_size=resolution)
                            self.current_x.set(f"{cur_x:.4f}")
                            self.current_y.set(f"{cur_y:.4f}")
                            start_time = time.time()
                            while time.time() - start_time < acq_time:
                                time.sleep(0.01)
                            self.tcp_client2(x, y)
                        #if self.scan_mode.get() == "Bidirectional":
                        #    for x in x_rangeb:
                        #        if not self.nanonis_running:
                        #           #print("Client 1 detected stop signal in x.")
                        #            break
                        #        current_x = start_x + x * resolution
                        #        cur_x, cur_y = self.rotate_point(current_x, current_y, center_x, center_y, rotation*(-1))
                        #        response = folme.XYPosSet(cur_x, cur_y, True)
                        #        start_time = time.time()
                        #        intensity_values = []
                        #        while time.time() - start_time < acq_time:
                        #            if self.dropdown_var.get() == "Height":
                        #                intensity_values.append(zctrl.ZPosGet())
                        #            elif self.dropdown_var.get() == "Current":
                        #                intensity_values.append(current.Get())
                        #        #end_time = time.time()
                        #        #total_time_ms = (end_time - start_time) * 1000  # Convert to milliseconds
                        #        if intensity_values:
                        #            intensity = sum(intensity_values) / len(intensity_values)  # Mean value
                        #        else:
                        #            intensity = 0
                    self.start_button.config(text="Start", font=self.arr18, bg="green")
                    self.index_x = -1
                    self.index_y = -1
                    self.send_stop_to_picoharp()
                    self.is_running = False
                    #print("Finish Scan Loop")
                    #self.client_socket1 = self.nanonis.close_socket()
                    #self.client_socket2 = self.client_socket2.close()
        except Exception as e:
            print(f"Client 1 error: {e}")

    # TCP client 2 function
    def tcp_client2(self, x, y):
        message = f"D".encode('utf-8')
        try:
            # Send data only if running
            if self.picoharp_connected:
                self.sock.sendall(message)
                data = b''
                while len(data) < 4:
                    packet = self.sock.recv(4 - len(data))
                    if not packet:
                        raise ConnectionError("Socket connection broken")
                    data += packet

                # Unpack the received data (intensity value)
                intensity_value = struct.unpack('!I', data)[0]
                self.intensity1.set(self.format_output(intensity_value))

                # Update the plot with the received intensity value for the given (x, y)
                if x >= 0 and y >=0:
                    self.update_intensity_plot(x, y, intensity_value)
                else:
                    return intensity_value

        except Exception as e:
            print(f"Error receiving data to Picoharp: {e}")

    def send_start_to_picoharp(self, binwidth):
        message = f"M{binwidth}M".encode('utf-8')
        try:
            if self.picoharp_connected:
                self.sock.sendall(message)
                #print("Sent 'Start' to server2")
                receive = self.sock.recv(1024).decode('utf-8')
        except Exception as e:
            print(f"Error sending Start to Picoharp: {e}")

    def send_stop_to_picoharp(self):
        message = f"S".encode('utf-8')
        try:
            if self.picoharp_connected:
                # Send "Stop" message to server2
                self.sock.sendall(message)
                #print("Sent 'Stop' to server2")
                receive = self.sock.recv(1024).decode('utf-8')
        except Exception as e:
            print(f"Error sending Stop to Picoharp: {e}")

    def update_intensity_plot(self, x, y, intensity_value):
        if self.is_running:
            frame_size = int(self.pixel.get())
            
            if self.raw_intensity1.shape != (frame_size, frame_size):
                new_intensity_data = np.zeros((frame_size, frame_size))
                self.raw_intensity1 = new_intensity_data
                self.im1.set_data(new_intensity_data)
                self.im1.set_extent((0, frame_size, 0, frame_size))
                self.ax1.set_xlim(0, frame_size)
                self.ax1.set_ylim(0, frame_size)
                self.ax1.figure.canvas.draw_idle()

            self.raw_intensity1[y, x] = intensity_value
            fitted_data1 = self.fitting_methods.get(self.fitting1.get(), twoDfittings.raw)(self.raw_intensity1)
            self.im1.set_data(fitted_data1)
            if self.manual_colorbar1 == False:
                if self.scan_mode.get() == "Backward":
                    if y == 0 and x == frame_size-1:
                        self.min1 = fitted_data1[y, x]
                        self.max1 = fitted_data1[y, x]
                    else:
                        val = fitted_data1[y, x]
                        self.min1 = min(self.min1, val)
                        self.max1 = max(self.max1, val)
                else:
                    if y == 0 and x == 0:
                        self.min1 = fitted_data1[y, x]
                        self.max1 = fitted_data1[y, x]
                    else:
                        val = fitted_data1[y, x]
                        self.min1 = min(self.min1, val)
                        self.max1 = max(self.max1, val)
                vmin=self.min1
                vmax=self.max1*(1+self.color_scale)
                self.im1.set_clim(vmin=vmin, vmax=vmax)
                self.vmin1.set(vmin)
                self.vmax1.set(vmax)
            self.canvas.draw_idle()

    def on_click(self, event):
        #if event.inaxes:
        if event.inaxes in [self.ax1]:
            # Get the current frame size (i.e., resolution)
            frame_size = int(self.pixel.get())
            #print(f"event.xdata: {event.xdata}, event.xdata: {event.ydata}")

            # Clamp the coordinates within valid bounds
            self.index_x = int(min(max(event.xdata, 0), frame_size - 1))
            self.index_y = int(min(max(event.ydata, 0), frame_size - 1))
            #print(f"self.index_x: {self.index_x}, self.index_y: {self.index_y}")

            # Update the crosshairs and the cursor positions on both maps
            self.update_crosshair(self.index_x, self.index_y)

    def on_scroll(self, event):
        # Only react if mouse is inside the axis (optional)
        if event.inaxes != self.ax1:
            return
        if not self.stepper_motor.kim001_connected:
            return
        if event.button == "up":
            self.stepper_motor.kim001.move_relative(self.stepper_motor.kim001_step)
        elif event.button == "down":
            self.stepper_motor.kim001.move_relative(-self.stepper_motor.kim001_step)
        else:
            return

    def on_key(self, event):
        frame_size = int(self.pixel.get())
        step = 1  # how many pixels to move per key press
        if self.index_x > -1 and self.index_y > -1:
            if event.key == "left":
                self.index_x = max(self.index_x - step, 0)
            elif event.key == "right":
                self.index_x = min(self.index_x + step, frame_size - 1)
            elif event.key == "up":
                self.index_y = max(self.index_y + step, 0)
            elif event.key == "down":
                self.index_y = min(self.index_y - step, frame_size - 1)

            self.update_crosshair(self.index_x, self.index_y)

    def update_crosshair(self, x, y):
        # Set the crosshair position on both maps
        self.crosshair1.set_data([x], [y])
        
        center_x = self.parse_input(self.center_x.get())
        center_y = self.parse_input(self.center_y.get())
        rotation = self.parse_input(self.rotation.get())
        frame = self.parse_input(self.frame.get())
        pixel = int(self.pixel.get())        
        resolution = frame / pixel
        start_x = center_x - (frame / 2)  # Start from the left
        start_y = center_y + (frame / 2)  # Start from the top
        
        current_x = start_x + x * resolution
        current_y = start_y - (frame-y-1) * resolution
        cur_x, cur_y = self.rotate_point(current_x, current_y, center_x, center_y, rotation*(-1))

        dx = cur_x - float(self.current_x.get())
        dy = cur_y - float(self.current_y.get())
        if abs(dx) < self.tol and abs(dy) < self.tol:
            return False
        # Update cursor x, y, and intensity values for both maps
        self.e70d2s.move_to(target_x=cur_x, target_y=cur_y, step_size=resolution)
        self.current_x.set(f"{cur_x:.4f}")
        self.current_y.set(f"{cur_y:.4f}")

        intensity1 = self.im1.get_array()[y, x]
        self.intensity1.set(self.format_output(intensity1))  # Update intensity for the first map

        # Redraw the canvas with updated crosshairs
        self.canvas.draw()

    def rotate_point(self, x, y, cx=0, cy=0, angle=0):
        # Convert angle to radians
        theta = math.radians(angle)

        # Translate point back to origin
        x_shifted = x - cx
        y_shifted = y - cy

        # Apply rotation matrix
        x_rotated = x_shifted * math.cos(theta) - y_shifted * math.sin(theta)
        y_rotated = x_shifted * math.sin(theta) + y_shifted * math.cos(theta)

        # Translate back to original position
        x_new = x_rotated + cx
        y_new = y_rotated + cy

        return x_new, y_new

    def parse_input(self, input_str):
        if input_str.strip() in ['0', '-0']:
            return 0.0  # Handle 0 and -0 explicitly
        
        # Replace comma with dot for consistent decimal point
        input_str = input_str.replace(',', '.').strip()
        
        try:
            # Check for unit suffix and convert to nanometers
            if input_str.endswith('n'):
                return float(input_str[:-1]) * 1e-9
            elif input_str.endswith('u'):
                return float(input_str[:-1]) * 1e-6 
            elif input_str.endswith('m'):
                return float(input_str[:-1]) * 1e-3
            else:
                # Assume the input is already in nanometers if no suffix
                return float(input_str)
        except ValueError:
            raise ValueError(f"Invalid input: {input_str}. Please enter a valid number.")

    def format_output(self, input_value):
        if 1e-15 < abs(input_value) <= 1e-12:
            return f"{input_value * 1e15:.2f}f"
        elif 1e-12 < abs(input_value) <= 1e-9:
            return f"{input_value * 1e12:.2f}p"
        elif 1e-9 < abs(input_value) <= 1e-6:
            return f"{input_value * 1e9:.2f}n"
        elif 1e-6 < abs(input_value) <= 1e-3:
            return f"{input_value * 1e6:.2f}u"
        elif 1e-3 < abs(input_value) <= 1:
            return f"{input_value * 1e3:.2f}m"
        elif 1 < abs(input_value) <= 1e3:
            return f"{int(input_value)}"
        elif 1e3 < abs(input_value) <= 1e6:
            return f"{input_value / 1e3:.2f}K"
        elif 1e6 < abs(input_value) <= 1e9:
            return f"{input_value / 1e6:.2f}M"
        else:
            return f"{input_value}"  # For other ranges, use scientific notation 

    def correct_scan_down_zigzag(self, data):
        corrected_data = np.zeros_like(data)
        
        # Fix the zigzag pattern
        for i in range(data.shape[0]):
            if i % 2 == 0:
                corrected_data[i] = data[i]  # Even rows stay the same
            else:
                corrected_data[i] = data[i][::-1]  # Reverse odd rows back

        # Flip the data vertically (top-to-bottom correction)
        corrected_data = np.flipud(corrected_data)

        return corrected_data

if __name__ == "__main__":
    root = tk.Tk()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    app = IntensityMapGUI(root)
    root.mainloop()
