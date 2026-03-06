import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import sys
import clr  # clr is part of the pythonnet package
import os
import math
import time
import serial
import threading
from System.Text import StringBuilder
import serial.tools.list_ports
from ctypes import cdll,c_long, c_ulong, c_uint32,byref,create_string_buffer,c_bool,c_char_p,c_int,c_int16,c_double, sizeof, c_voidp
from TLPMX import TLPMX
from TLPMX import TLPM_DEFAULT_CHANNEL
from ag_uc2_8 import PiezoUC28
from thorlabs_control import KIM001Controller

class FilterWheelCanvas(tk.Canvas):
    def __init__(self, parent, image_path, size=350, **kwargs):
        super().__init__(parent, width=size, height=size, bg="white", highlightthickness=0, **kwargs)
        self.size = size
        self.center = size // 2
        self.spot_radius = 8
        self.current_angle = 90  # degrees
        self.angle_callback = None  # function to call when clicked

        # Load base image
        self.base_image = Image.open(image_path).resize((size, size), Image.LANCZOS)
        self.tk_image = None
        self.img_id = None

        # Draw first time
        self.update_angle(0)

        self.bind("<Button-1>", self.on_click)

    def draw_spot(self, angle_deg):
        """Draw laser spot at given angle."""
        cx, cy = self.center, self.center
        angle_rad = math.radians(angle_deg)
        x = cx + self.radius * 0.8 * math.cos(angle_rad)
        y = cy - self.radius * 0.8 * math.sin(angle_rad)
        self.create_oval(x - self.spot_radius, y - self.spot_radius,
                         x + self.spot_radius, y + self.spot_radius,
                         fill="red")

    def update_angle(self, angle_deg):
        """Rotate wheel image to given angle and redraw."""
        pil_angle = angle_deg % 360
        self.current_angle = pil_angle
        rotated = self.base_image.rotate(-pil_angle, resample=Image.BICUBIC, center=(self.center, self.center))
        self.tk_image = ImageTk.PhotoImage(rotated)

        self.delete("all")
        self.img_id = self.create_image(self.center, self.center, image=self.tk_image)

        # Update the existing wheel image
        self.itemconfig(self.img_id, image=self.tk_image)

        # Ensure the laser spot is drawn ONCE at fixed position
        self.delete("spot")
        spot_x, spot_y = self.center, self.center - 100   # fixed position
        self.create_oval(spot_x - self.spot_radius, spot_y - self.spot_radius,
                            spot_x + self.spot_radius, spot_y + self.spot_radius,
                            fill="red", tags="spot"
        )

    def on_click(self, event):
        """Click → compute angle → call callback if exists."""
        dx, dy = event.x - self.center, self.center - event.y
        angle_deg  = math.degrees(math.atan2(dy, dx)) % 360
        angle = angle_deg + self.current_angle - 90.0
        if self.angle_callback:
            self.angle_callback(angle)

class DialCanvas(tk.Canvas):
    def __init__(self, parent, size=300, **kwargs):
        super().__init__(parent, width=size, height=size, bg="white", highlightthickness=0, **kwargs)
        self.size = size
        self.center = size // 2
        self.radius = size * 0.4
        self.pointer_len = self.radius * 0.9
        self.left_angle = 205   # degrees (left-bottom)
        self.right_angle = 290   # degrees (right-bottom)
        self.divided_angle = ((self.right_angle-self.left_angle)/4)%360
        self.current_angle = 0
        self.angle_callback = None

        self.draw_dial()
        self.draw_pointer(self.current_angle)

        self.bind("<Button-1>", self.on_click)

    def draw_dial(self):
        """Draw arc with ticks and labels."""
        self.create_arc(self.center - self.radius, self.center - self.radius,
                        self.center + self.radius, self.center + self.radius,
                        start=self.right_angle, extent=360-(self.right_angle-self.left_angle), style="arc", width=5)

        # MIN label
        self.create_text(self.center - self.radius * 0.9, self.center + self.radius * 0.53,
                         text="MIN", font=("Arial", 18, "bold"))

        # MAX label
        self.create_text(self.center + self.radius * 0.3, self.center + self.radius * 1.05,
                         text="MAX", font=("Arial", 18, "bold"))

    def draw_pointer(self, angle_deg):
        """Draw a red triangular pointer rotated to the given angle."""
        self.delete("pointer")
        angle_rad = math.radians(angle_deg)

        # Tip of the pointer (outer point)
        tip_x = self.center + self.pointer_len * math.cos(angle_rad)
        tip_y = self.center - self.pointer_len * math.sin(angle_rad)

        # Triangle base width and distance behind the tip
        base_width = 20
        base_back = 30

        # Compute left/right base points by rotating ±90° around the angle
        left_angle = angle_rad + math.pi / 2
        right_angle = angle_rad - math.pi / 2

        base_x = self.center + (self.pointer_len - base_back) * math.cos(angle_rad)
        base_y = self.center - (self.pointer_len - base_back) * math.sin(angle_rad)

        left_x = base_x + (base_width / 2) * math.cos(left_angle)
        left_y = base_y - (base_width / 2) * math.sin(left_angle)

        right_x = base_x + (base_width / 2) * math.cos(right_angle)
        right_y = base_y - (base_width / 2) * math.sin(right_angle)

        # Draw triangle
        self.create_polygon(
            tip_x, tip_y,
            left_x, left_y,
            right_x, right_y,
            fill="red", tags="pointer"
        )
        self.current_angle = angle_deg

    def on_click(self, event):
        """Convert click → angle (restricted between MIN and MAX)."""
        dx, dy = event.x - self.center, self.center - event.y
        angle_deg = math.degrees(math.atan2(dy, dx)) % 360
        angle = self.current_angle
        force_direction = None
        
        # Restrict within dial range
        if angle_deg <= self.left_angle or angle_deg >= self.right_angle:
            angle = angle_deg
        elif angle_deg > self.left_angle and angle_deg <= self.left_angle + self.divided_angle:
            angle = self.left_angle
        elif angle_deg < self.right_angle and angle_deg >= self.right_angle - self.divided_angle:
            angle = self.right_angle

        force_direction = self.crosses_forbidden(self.current_angle, angle)
        # Update pointer
        self.draw_pointer(angle)

        # Callback to motor
        if self.angle_callback:
            self.angle_callback(angle, force_direction)

    def convert_angle(self, input_angle):
        diff = input_angle - self.right_angle
        if diff < 0:
            return diff + 360
        else:
            return diff

    def crosses_forbidden(self, start, end):
        s = self.convert_angle(start)
        e = self.convert_angle(end)
        #print("s:",s, "e:",e)

        if e > s:
            return 0
        elif e < s:
            return 1

class NDFilterGUI:
    def __init__(self, parent_frame):
        self.root = parent_frame
        self.arr18 = ('Arial', 18)
        self.arr24 = ('Arial', 24)

        self.baud_rate = 115200

        # Each motor will have its own parameters
        self.motors = {}
        for motor_id in range(2):
            self.motors[motor_id] = {
                "gear_ratio": 100,
                "full_step_angle": 18.00,
                "half_step": True,
                "current_position_steps": 0,
                "speed_var": tk.DoubleVar(value=100),
                "goto_angle_var": tk.StringVar(value="0.0"),
                "direction": 1,
                "motor_running": False
            }
            self.update_step_params(motor_id)
        self.motor_speed_lower = 10000
        self.motor_speed_upper = 1
        self.pwm_freq = 50000;
        self.pwm_res = 8;
        self.pwm_d = 2.0;
        self.pwm_dmin = 0;
        self.pwm_dmax = 5;

        self.left_angle = 205   # degrees (left-bottom)
        self.right_angle = 290   # degrees (right-bottom)

        self.tlPM = TLPMX()
        self.pm16_wavelength = tk.StringVar(value="532")
        self.pm16_power = tk.StringVar(value="0.0")
        self.piezo = PiezoUC28(1)
        self.ag_uc2_speed_var = tk.DoubleVar(value=20)
        self.ag_uc2_port_var = tk.StringVar(value="COM2")
        self.ag_uc2_voltage_lower = 17
        self.ag_uc2_voltage_upper = 50
        self.ag_uc2_step_lower = 5
        self.ag_uc2_step_upper = 2000
        self.kim001 = KIM001Controller()
        self.kim001_speed_var = tk.DoubleVar(value=20)
        self.kim001_step_lower = 10
        self.kim001_step_upper = 1000
        self.kim001_step = self.map_speed(self.kim001_speed_var.get(),self.kim001_step_lower,self.kim001_step_upper)
        self.arduino_port_var = tk.StringVar(value="COM1")
        self.arduino = None
        self.ag_uc2_connected = False
        self.kim001_connected = False
        self.pm16_connected = False
        self.pm16_thread_running = False
        self.arduino_connected = False

        self.build_ui()

    # -------- UI --------
    def build_ui(self):
        # Arduino Serial Port Selection
        self.arduino_port_label = tk.Label(self.root, text="Arduino Port", font=self.arr18)
        self.arduino_port_label.grid(row=0, column=0, padx=5, pady=5)

        self.arduino_port_combobox = ttk.Combobox(self.root, textvariable=self.arduino_port_var, width=6, font=self.arr18)
        self.arduino_port_combobox.grid(row=0, column=1, padx=5, pady=5)
        self.arduino_port_combobox.bind("<Button-1>", self.update_ports(self.arduino_port_combobox, self.arduino_port_var))

        self.arduino_connect_button = tk.Button(self.root, text="Connect", command=self.connect_arduino,
                                        font=self.arr18, bg="red", fg="white")
        self.arduino_connect_button.grid(row=0, column=2, padx=5, pady=5)

        # NDF Filter
        self.config_button1 = tk.Button(self.root, text="Config & Ctrl NDF", command=lambda: self.open_config_control(0), font=self.arr18)
        self.config_button1.grid(row=0, column=3, padx=5)
        self.config_button1.config(state='disabled')

        # Laser Flip
        self.config_button2 = tk.Button(self.root, text="Config & Ctrl LSFP", command=lambda: self.open_config_control(1), font=self.arr18)
        self.config_button2.grid(row=0, column=4, padx=5)
        self.config_button2.config(state='disabled')

        self.flip_button1 = tk.Button(self.root, text="LS Flip", command=lambda: self.flip_angle(motor_id=1,ang=-120), font=self.arr18)
        self.flip_button1.grid(row=0, column=5, padx=5, pady=5)
        self.flip_button1.config(state='disabled')
        
        self.motors[1]["flip_button"] = self.flip_button1

        #PM16-120
        self.pm16_label = tk.Label(self.root, text="PM16-120", font=self.arr18)
        self.pm16_label.grid(row=1, column=0, padx=5, pady=5)

        self.pm16_connect_button = tk.Button(self.root, text="Connect", command=self.connect_pm16,
                                        font=self.arr18, bg="red", fg="white")
        self.pm16_connect_button.grid(row=1, column=2, padx=5, pady=5)

        # Light adjuster
        self.config_button4 = tk.Button(self.root, text="Config & Ctrl LGT", command=lambda: self.open_config_pwm(), font=self.arr18)
        self.config_button4.grid(row=1, column=3, padx=5)
        self.config_button4.config(state='disabled')

        # ND Filter Wheel Go-to angle
        self.build_motor_controls(self.root, 0, goto=1, row_start=2)

        # ND Filter Wheel visualization
        self.wheel_canvas = FilterWheelCanvas(self.root, image_path="ND1.png", size=350)
        self.wheel_canvas.grid(row=5, column=0, columnspan=3, pady=20)
        self.wheel_canvas.angle_callback = self.on_wheel_click
        #self.wheel_canvas.grid(row=5, column=0, columnspan=3, pady=20)
        #self.wheel_canvas.angle_callback = self.on_wheel_click

        # Laser power measure
        pm16pad_frame = tk.Frame(self.root)
        pm16pad_frame.grid(row=5, column=3, sticky=tk.N)  # occupies ONE cell only
        self.pm16_wavelength_label = tk.Label(pm16pad_frame, text="Wavelength (nm)", font=self.arr18)
        self.pm16_wavelength_label.grid(row=1, column=0)
        self.pm16_wavelength_entry = tk.Entry(pm16pad_frame, font=self.arr18, width=5, textvariable=self.pm16_wavelength)
        self.pm16_wavelength_entry.bind("<Return>", self.pm16_wavelength_value_entered)
        self.pm16_wavelength_entry.bind("<FocusOut>", self.pm16_wavelength_value_entered) 
        self.pm16_wavelength_entry.grid(row=2, column=0, padx=5, sticky=tk.E)
        tk.Label(pm16pad_frame, text="Power (W):", font=self.arr18).grid(row=3, column=0, sticky=tk.W)
        self.pm16_power_display = tk.Label(pm16pad_frame, textvariable=self.pm16_power, font=self.arr24, width=8)
        self.pm16_power_display.grid(row=4, column=0, padx=0, sticky="e")

        # Connect canvas clicks to motor control
        self.dial_label = tk.Label(self.root, text="White Light Dial", font=self.arr18)
        self.dial_label.grid(row=4, column=4, columnspan=3, pady=(0,0))
        self.dial_canvas = DialCanvas(self.root, size=300)
        self.dial_canvas.grid(row=5, column=4, columnspan=3, pady=(20,0), sticky="n")
        self.dial_canvas.angle_callback = self.on_dial_click

        mpad_label_frame = tk.Frame(self.root)
        mpad_label_frame.grid(row=6, column=0, sticky=tk.N)  # occupies ONE cell only
        mpad_port_frame = tk.Frame(self.root)
        mpad_port_frame.grid(row=6, column=1, sticky=tk.N)  # occupies ONE cell only 
        mpad_connect_frame = tk.Frame(self.root)
        mpad_connect_frame.grid(row=6, column=2, sticky=tk.N)  # occupies ONE cell only   

        # ag_uc2_8 Serial Port Selection
        self.ag_uc2_port_label = tk.Label(mpad_label_frame, text="AG-UC2 Port", font=self.arr18)
        self.ag_uc2_port_label.grid(row=0, column=0, padx=5, pady=5, sticky="n")

        self.ag_uc2_combobox = ttk.Combobox(mpad_port_frame, textvariable=self.ag_uc2_port_var, width=6, font=self.arr18)
        self.ag_uc2_combobox.grid(row=0, column=0, padx=5, pady=5, sticky="s")
        self.ag_uc2_combobox.bind("<Button-1>", self.update_ports(self.ag_uc2_combobox, self.ag_uc2_port_var))

        self.ag_uc2_connect_button = tk.Button(mpad_connect_frame, text="Connect", command=self.connect_ag_uc2,
                                        font=self.arr18, bg="red", fg="white")
        self.ag_uc2_connect_button.grid(row=0, column=0, padx=5, pady=5, sticky="n")

        # KIM001 Controller
        self.kim001_label = tk.Label(mpad_label_frame, text="KIM001", font=self.arr18)
        self.kim001_label.grid(row=1, column=0, padx=5, pady=5, sticky="n")

        self.kim001_connect_button = tk.Button(mpad_connect_frame, text="Connect", command=self.connect_kim001,
                                        font=self.arr18, bg="red", fg="white")
        self.kim001_connect_button.grid(row=1, column=0, padx=5, pady=5, sticky="s")

        # XY movement
        dpad_frame = tk.Frame(self.root)
        dpad_frame.grid(row=6, column=3)  # occupies ONE cell only

        btn_style = {"font": ("Segoe UI Symbol", 24, "bold"), "width": 3, "height": 0}
        btn_stop_style = {"font": ("Arial", 24, "bold"), "fg": "red", "width": 3, "height": 1}

        self.btn_up = tk.Button(dpad_frame, text="⬆", command=lambda:self.move_xyz("Y+"), **btn_style)
        self.btn_up.grid(row=0, column=1, pady=0, sticky="s")
        self.btn_up.config(state="disabled")

        self.btn_down = tk.Button(dpad_frame, text="⬇", command=lambda:self.move_xyz("Y-"), **btn_style)
        self.btn_down.grid(row=2, column=1, pady=0, sticky="n")
        self.btn_down.config(state="disabled")

        self.btn_left = tk.Button(dpad_frame, text="⬅", command=lambda:self.move_xyz("X-"), **btn_style)
        self.btn_left.grid(row=1, column=0, padx=0, sticky="e")
        self.btn_left.config(state="disabled")

        self.btn_right = tk.Button(dpad_frame, text="⮕", command=lambda:self.move_xyz("X+"), **btn_style)
        self.btn_right.grid(row=1, column=2, padx=0, sticky="w")
        self.btn_right.config(state="disabled")
        
        self.btn_stop_xy = tk.Button(dpad_frame, text="●", command=lambda:self.move_xyz("STOPXY"), **btn_stop_style)
        self.btn_stop_xy.grid(row=1, column=1, ipadx=0, ipady=0)
        self.btn_stop_xy.config(state="disabled")
        self.xy_slide = self.speed_slider (self.root, row=7, column=2, motor_id=-1)

        # Z movement
        zpad_frame = tk.Frame(self.root)
        zpad_frame.grid(row=6, column=4, sticky="ne")  # occupies ONE cell only
            
        z_style = {"font": ("Arial", 24, "bold"), "width": 3, "height": 1}
        self.btn_z_plus = tk.Button(zpad_frame, text="▲", command=lambda:self.move_xyz("Z+"),**z_style)
        self.btn_z_plus.grid(row=0, column=0, sticky="s")
        self.btn_z_plus.config(state="disabled")

        self.btn_z_minus = tk.Button(zpad_frame, text="▼", command=lambda:self.move_xyz("Z-"),**z_style)
        self.btn_z_minus.grid(row=1, column=0, sticky="n")
        self.btn_z_minus.config(state="disabled")
        self.z_slide = self.speed_slider (self.root, row=7, column=4, motor_id=-2)

    def build_motor_controls(self, parent, motor_id, goto=0, row_start=0):
        motor = self.motors[motor_id]
        if goto == 0:
            # Speed Slider and Entry
            self.speed_slider(parent,row=row_start,motor_id=motor_id)
            
            # Direction button
            dir_button = tk.Button(parent, text="Forward", font=self.arr18, command=lambda: self.toggle_direction(motor_id))
            dir_button.grid(row=row_start, column=4, columnspan=2, padx=5, pady=5)
            motor["dir_button"] = dir_button

            # Zero angle
            zero_button = tk.Button(parent, text="Zero", command=lambda: self.zero_angle(motor_id), font=self.arr18)
            zero_button.grid(row=row_start+2, column=3)

            motor["zero_button"] = zero_button

            # Start/Stop Toggle Button
            toggle_button = tk.Button(parent, text="Start Free Running", command=lambda: self.toggle_motor(motor_id),
                                    font=self.arr18, bg="green", fg="white", width=15, height=2)
            toggle_button.grid(row=row_start+3, column=1, columnspan=2, pady=10)
            motor["toggle_button"] = toggle_button
        
        # Go-to angle
        goto_label = tk.Label(parent, text="Go To (°)", font=self.arr18)
        goto_label.grid(row=row_start+2, column=0, padx=5, pady=5)
        goto_entry = tk.Entry(parent, textvariable=motor["goto_angle_var"], font=self.arr18, width=6)
        goto_entry.grid(row=row_start+2, column=1, padx=5, pady=5)
        motor["goto_entry"] = goto_entry

        goto_button = tk.Button(parent, text="Move", bg="orange", command=lambda: self.go_to_angle(motor_id), font=self.arr18)
        goto_button.grid(row=row_start+2, column=2, padx=5, pady=5)
        motor["goto_button"] = goto_button

        if goto == 1:
            goto_button.config(state='disabled')

        #if motor_id == 0:
        #    goto_button.config(state='disabled')
        #    zero_button.config(state='disabled')
        #    toggle_button.config(state='disabled')
    def speed_slider (self, frame, row, column=0, motor_id=0):
        if motor_id > -1:
            speed_label = tk.Label(frame, text=f"Speed (%)", font=self.arr18).grid(row=row, column=column, padx=5, pady=5)
            motor = self.motors[motor_id]
            speed_slider = tk.Scale(frame, from_=0.0, to=100.0, orient=tk.HORIZONTAL,
                                resolution=0.01, font=self.arr18, length=250, variable=motor["speed_var"], showvalue=0)
        elif motor_id == -1:
            speed_label = tk.Label(frame, font=self.arr18).grid(row=row, column=column, padx=5, pady=5)
            speed_slider = tk.Scale(frame, from_=0.0, to=100.0, orient=tk.HORIZONTAL,
                                resolution=0.01, font=self.arr18, length=250, variable=self.ag_uc2_speed_var, showvalue=0)
        elif motor_id == -2:
            speed_label = tk.Label(frame, font=self.arr18).grid(row=row, column=column, padx=5, pady=5)
            speed_slider = tk.Scale(frame, from_=0.0, to=100.0, orient=tk.HORIZONTAL,
                                resolution=0.01, font=self.arr18, length=250, variable=self.kim001_speed_var, showvalue=0)
        #speed_slider.set(100)
        speed_slider.grid(row=row, column=column+1, columnspan=2, padx=5, pady=5, sticky="w")
        if motor_id > -1:
            motor["speed_slider"] = speed_slider

        if motor_id > -1:
            speed_entry = tk.Entry(frame, textvariable=motor["speed_var"], font=self.arr18, width=5)
            speed_entry.grid(row=row, column=column+3, padx=5, pady=5, sticky="w")
        elif motor_id == -1:
            speed_entry = tk.Entry(frame, textvariable=self.ag_uc2_speed_var, font=self.arr18, width=5)
            speed_entry.grid(row=row, column=column+2, padx=40, pady=5, sticky="w")
        elif motor_id == -2:
            speed_entry = tk.Entry(frame, textvariable=self.kim001_speed_var, font=self.arr18, width=5)
            speed_entry.grid(row=row, column=column+3, padx=0, pady=5, sticky="w")
        speed_entry.bind("<Return>", lambda e: self.on_speed_entry_change(motor_id))
        speed_entry.bind("<FocusOut>", lambda e: self.on_speed_entry_change(motor_id))
        if motor_id > -1:
            motor["speed_entry"] = speed_entry

    def on_wheel_click(self, angle_deg):
        """Handle user clicking on wheel → move motor to that angle."""
        self.motors[0]["goto_angle_var"].set(f"{(angle_deg%360):.1f}")
        self.go_to_angle(0)  # move motor 0

    def on_dial_click(self, angle_deg, force_direction=None):
        """Move motor according to dial click (only within arc)."""
        diff = self.left_angle-angle_deg
        if diff < 0:
            diff = self.left_angle+ 360-angle_deg
        transf = diff/(self.left_angle+360-self.right_angle)
        self.pwm_d = transf*(self.pwm_dmax-self.pwm_dmin)+self.pwm_dmin        
        if self.arduino_connected:
            cmd = f"PWM SET {self.pwm_d}\n"
            self.arduino.write(cmd.encode())
            self.arduino.flush() 
    
    def convert_pwm_to_angle(self):
        transf = (self.pwm_d-self.pwm_dmin)/(self.pwm_dmax-self.pwm_dmin)
        angle = transf*(self.left_angle+360-self.right_angle)+self.left_angle
        if angle > 360:
            angle = angle - 360
        return angle
    
    def update_ports(self, combobox, variable, event=None):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        combobox["values"] = ports    
        if ports and variable.get() not in ports:
            variable.set(ports[0])

    def connect_arduino(self):
        motor = self.motors[0]
        if not self.arduino_connected:

            selected_port = self.arduino_port_var.get().strip()
            if not selected_port:
                print("No serial port selected!")
                return

            available_ports = [port.device for port in serial.tools.list_ports.comports()]
            ports_to_try = []
            if selected_port and selected_port in available_ports:
                ports_to_try.append(selected_port)  
            ports_to_try += [p for p in available_ports if p != selected_port]

            for port in ports_to_try:
                try:
                    self.arduino = serial.Serial(port, self.baud_rate, timeout=1, write_timeout=1)
                    try:
                        if self.read_id() == "STEPPER":
                            try:
                                self.arduino_connected = True
                                self.arduino_port_var.set(port)
                                # Read config for both motors
                                for motor_id in self.motors.keys():
                                    self.request_config(motor_id)
                                    cur_angle = self.step_to_angle(motor_id)
                                    self.motors[motor_id]["goto_angle_var"].set(f"{(cur_angle%360):.1f}")
                                    if motor_id == 0:
                                        #print(f"Initial angle = {(self.step_to_angle(0)):.1f}")
                                        self.wheel_canvas.update_angle(self.step_to_angle(0))
                                    elif motor_id == 1:
                                        #print(f"Initial angle: {(cur_angle%360):.1f}")
                                        if cur_angle == 0:
                                            self.flip_button1.config(text="Flip Up", bg="green")
                                        else:
                                            self.flip_button1.config(text="Flip Down", bg="red")
                                    #elif motor_id == 2:
                                    #    if cur_angle == 0:
                                    #        self.flip_button2.config(text="Flip Up", bg="green")
                                    #    else:
                                    #        self.flip_button2.config(text="Flip Down", bg="red")
                                    #elif motor_id == 3:
                                    #    self.dial_canvas.draw_pointer(self.step_to_angle(3))
                                self.request_pwm_config()
                                self.dial_canvas.draw_pointer(self.convert_pwm_to_angle())                                
                                self.arduino_connect_button.config(text="Connected", bg="green")
                                self.config_button1.config(state="normal")
                                self.config_button2.config(state="normal")
                                self.config_button4.config(state="normal")
                                self.flip_button1.config(state='normal')
                                #self.flip_button2.config(state='normal')
                                #for key in ["goto_button", "zero_button", "toggle_button"]:
                                for key in ["goto_button"]:
                                    if key in motor:  # only touch if it exists
                                        motor[key].config(state="normal")
                                break
                            except Exception as e:
                                #print(f"Read Configuration failed: {e}")
                                # Clean up serial connection and exit early
                                self.arduino.close()
                                self.arduino = None
                                self.arduino_connected = False
                                continue
                    except Exception as e:
                        continue
                except serial.SerialException as e:
                    #print(f"SerialException: {e}")
                    continue
        else:
            if self.arduino and self.arduino.is_open:
                try:
                    self.arduino.close()
                    #print("Serial port closed.")
                except Exception as e:
                    print(f"Error closing serial port: {e}")
            self.arduino = None
            self.arduino_connected = False
            self.arduino_connect_button.config(text="Disconnected", bg="red")
            self.config_button1.config(state="disabled")
            self.config_button2.config(state="disabled")
            self.config_button4.config(state="disabled")
            self.flip_button1.config(state='disabled')
            #self.flip_button2.config(state='disabled')

            for key in ["goto_button", "zero_button", "toggle_button"]:
                if key in motor:
                    motor[key].config(state="disabled")

    def connect_ag_uc2(self):
        if not self.ag_uc2_connected:
            conn = self.piezo.discover_and_open_device(self.ag_uc2_port_var.get())
            if conn != "":
                self.ag_uc2_port_var.set(conn)
                self.ag_uc2_connect_button.config(text="Connected", bg="green")
                self.ag_uc2_connected = True
                self.btn_up.config(state="normal")
                self.btn_down.config(state="normal")
                self.btn_left.config(state="normal")
                self.btn_right.config(state="normal")
                self.btn_stop_xy.config(state="normal")
        else:
            self.ag_uc2_connect_button.config(text="Disconnect", bg="red")
            self.ag_uc2_connected = False
            self.btn_up.config(state="disabled")
            self.btn_down.config(state="disabled")
            self.btn_left.config(state="disabled")
            self.btn_right.config(state="disabled")
            self.btn_stop_xy.config(state="disabled")
 
    def connect_pm16(self):
        deviceCount = c_uint32()
        resourceName = create_string_buffer(1024)
        if not self.pm16_connected:
            self.tlPM.findRsrc(byref(deviceCount))
            if deviceCount.value > 0:
                self.pm16_connect_button.config(text="Connected", bg="green")
                self.pm16_connected = True
                self.pm16_thread_running = True
                self.tlPM.getRsrcName(c_int(0), resourceName)
                self.tlPM.open(resourceName, c_bool(True), c_bool(True))
                self.tlPM.setWavelength(c_double(float((self.pm16_wavelength.get()))),TLPM_DEFAULT_CHANNEL)
                self.tlPM.setPowerAutoRange(c_int16(1),TLPM_DEFAULT_CHANNEL)
                self.tlPM.setPowerUnit(c_int16(0),TLPM_DEFAULT_CHANNEL)
                self.pm16_thread = threading.Thread(target=self.read_pm16_data)
                self.pm16_thread.start()
        else:
            self.pm16_connect_button.config(text="Disconnect", bg="red")
            self.pm16_connected = False
            self.pm16_thread_running = False
            self.tlPM.close()

    def connect_kim001(self):
        if not self.kim001_connected:
            self.kim001.connect()
            self.kim001_connect_button.config(text="Connected", bg="green")
            self.kim001_connected = True
            self.btn_z_plus.config(state="normal") 
            self.btn_z_minus.config(state="normal") 
        else:
            self.kim001.disconnect()
            self.kim001_connect_button.config(text="Disconnect", bg="red")
            self.kim001_connected = False
            self.btn_z_plus.config(state="disabled") 
            self.btn_z_minus.config(state="disabled") 

    def read_id(self):
        cmd = f"ID\n"
        self.arduino.write(cmd.encode())
        self.arduino.flush()
        response = self.arduino.readline().decode().strip()
        return response

    def request_config(self, motor_id):
        if self.arduino_connected:
            #print(motor_id)
            cmd = f"READ {motor_id}\n"
            self.arduino.write(cmd.encode())
            self.arduino.flush()
            response = self.arduino.readline().decode().strip()
            #print(response)
            try:
                parts = response.split(',')
                self.motors[motor_id]["gear_ratio"] = float(parts[0])
                self.motors[motor_id]["full_step_angle"] = float(parts[1])
                self.motors[motor_id]["half_step"] = bool(int(parts[2]))
                self.motors[motor_id]["current_position_steps"] = int(parts[3])
                self.update_step_params(motor_id)
            except Exception as e:
                raise RuntimeError(f"Invalid config for motor {motor_id}: {response}") from e

    def request_pwm_config(self):
        if self.arduino_connected:
            cmd = f"PWM GET\n"
            self.arduino.write(cmd.encode())
            self.arduino.flush()
            response = self.arduino.readline().decode().strip()
            #print(response)
            try:
                parts = response.split(',')
                self.pwm_d = float(parts[0])
                self.pwm_freq = int(parts[1])
                self.pwm_res = int(parts[2])
                self.pwm_dmin = int(parts[3])
                self.pwm_dmax = int(parts[4])
            except Exception as e:
                raise RuntimeError(f"Invalid config for pwm: {response}") from e

    def on_speed_entry_change(self, motor_id, event=None):
        if motor_id > -1:
            motor = self.motors[motor_id]
            val = float(motor["speed_var"].get())
            if 0.0 <= val <= 100.0:
                motor["speed_slider"].set(val)
        elif motor_id == -1:
            val = float(self.ag_uc2_speed_var.get())
        elif motor_id == -2:
            val = float(self.kim001_speed_var.get())
        else:
            print("Error: Invalid number for speed.")            

    def toggle_direction(self, motor_id):
        motor = self.motors[motor_id]
        motor["direction"] = 1 - motor["direction"]
        dir_text = "Forward" if motor["direction"] == 1 else "Backward"
        motor["dir_button"].config(text=f"{dir_text}")

    def go_to_angle(self, motor_id, flip=False, angle=90.0, force_direction=None):
        super_method = getattr(super(type(self), self), "go_to_angle", None)
        if super_method:
            super_method(motor_id, flip, angle)

        motor = self.motors[motor_id]
        if self.arduino_connected and self.arduino:
            try:
                if flip == False:
                    target_angle = float(motor["goto_angle_var"].get().replace(',', '.')) % 360.00
                else:
                    target_angle = float(angle) % 360.00
                step_angle = self.get_step_angle(motor_id)
                steps_per_rev = self.get_steps_per_rev(motor_id)
                target_steps = round(target_angle / step_angle)
                delta_steps = (target_steps - motor["current_position_steps"]) % steps_per_rev

                #if delta_steps > steps_per_rev / 2:
                #    direction = 1
                #    steps_to_move = steps_per_rev - delta_steps
                #else:
                #    direction = 0
                #    steps_to_move = delta_steps
                if force_direction is not None:
                    # Explicit direction
                    direction = force_direction
                    if direction == 0:  # CW
                        steps_to_move = delta_steps
                    else:  # CCW
                        steps_to_move = (steps_per_rev - delta_steps) % steps_per_rev
                else:
                    # Use shortest-path logic if allowed
                    if delta_steps > steps_per_rev / 2:
                        direction = 1  # CCW
                        steps_to_move = steps_per_rev - delta_steps
                    else:
                        direction = 0  # CW
                        steps_to_move = delta_steps

                if flip == True:
                    flip_btn = motor.get("flip_button")
                    flip_btn.config(text="Flipping", bg="orange")
                else:
                    if "goto_button" in motor and motor["goto_button"].winfo_exists():
                        motor["goto_button"].config(text="Moving", bg="red")
                    #motor["toggle_button"].config(state='disabled')
                self.root.update_idletasks()
                speed = self.map_speed(motor["speed_var"].get(),self.motor_speed_lower,self.motor_speed_upper)
                command = f"SET {motor_id} {speed} {direction} {steps_to_move}\n"
                #print("current_position_steps = ",target_steps)
                #print("Sending: ",command)
                self.arduino.write(command.encode())
                self.arduino.flush()

                deadline = time.time() + 10  # 10-second timeout
                while time.time() < deadline:
                    if self.arduino.in_waiting:
                        response = self.arduino.readline().decode().strip()
                        if response.startswith("DONE"):
                            #print("Response from Arduino:", response)
                            try:
                                _, motor_id_str, current_step_str = response.split()
                                #print(f"Current step count: {int(current_step)}")
                            except ValueError:
                                print("Malformed DONE response:", response)
                            break
                    else:
                        #print("NOT OK")
                        time.sleep(0.05)  # Avoid CPU spin
                motor["current_position_steps"] = target_steps
                if motor_id == 0:
                    #print(f"Set step: {self.motors[0]["current_position_steps"]}")
                    #print(f"Set angle: {self.step_to_angle(0)}")
                    self.wheel_canvas.update_angle(self.step_to_angle(0))
                    self.request_config(0)
                    #print(f"Act step: {self.motors[0]["current_position_steps"]}")
                    #print(f"Act angle: {self.step_to_angle(0)}")

                if flip == True:
                    flip_btn = motor.get("flip_button")
                    #print(f"Current angle: {self.step_to_angle(motor_id)}")
                    #if flip_btn and flip_btn.winfo_exists():
                    if self.step_to_angle(motor_id) == 0 or self.step_to_angle(motor_id) == 180:
                        flip_btn.config(text="Flip Up", bg="green")
                        #print("Flip Up")
                    else:
                        #print("Flip Down")
                        flip_btn.config(text="Flip Down", bg="red")  
                else:
                    if "goto_button" in motor and motor["goto_button"].winfo_exists():
                        motor["goto_button"].config(text="Move", bg="orange")
                    #motor["toggle_button"].config(state='normal')

            except ValueError:
                print("Invalid angle input.")

    def zero_angle(self, motor_id):
        motor = self.motors[motor_id]
        motor["current_position_steps"] = 0
        if self.arduino_connected:
            cmd = f"ZERO {motor_id}\n"
            self.arduino.write(cmd.encode())
            self.arduino.flush()

    def toggle_motor(self, motor_id):
        motor = self.motors[motor_id]
        if self.arduino and self.arduino.is_open:
            if not motor["motor_running"]:
                try:
                    speed = self.map_speed(motor["speed_var"].get(),self.motor_speed_lower,self.motor_speed_upper)
                    direction = motor["direction"]
                    self.arduino.write(f"SET {motor_id} {speed} {direction}\n".encode())
                    self.arduino.flush()
                    self.arduino.write(f"START {motor_id}\n".encode())
                    self.arduino.flush()
                    motor["goto_button"].config(state="disabled")
                    motor["toggle_button"].config(text="Running", bg="red")
                    motor["motor_running"] = True
                except Exception as e:
                    print(f"Error starting motor: {e}")
            else:
                try:
                    self.arduino.write(f"STOP {motor_id}\n".encode())
                    self.arduino.flush()
                    motor["goto_button"].config(text="Start Free Running", bg="green")
                    motor["toggle_button"].config(state="normal")
                    motor["motor_running"] = False
                except Exception as e:
                    print(f"Error stopping motor: {e}")

    def open_config_control(self, motor_id):
        motor = self.motors[motor_id]

        win = tk.Toplevel(self.root)
        if motor_id == 0:
            win.title("NDF Motor - Config & Control")
        elif motor_id == 1:
            win.title("LSLF Flip Motor - Config & Control")
        elif motor_id == 2:
            win.title("BSLF Flip Motor - Config & Control")
        elif motor_id == 3:
            win.title("Light Motor - Config & Control")

        # Motor control section
        #control_frame = tk.LabelFrame(win, text="Flip Motor Control", font=self.arr18, padx=10, pady=10)
        control_frame = tk.LabelFrame(win, font=self.arr18, padx=10, pady=10)
        control_frame.grid(row=4, column=0, columnspan=2, pady=10, sticky="ew")
        self.build_motor_controls(control_frame, motor_id, row_start=0)

        # Config fields
        tk.Label(win, text="Gear Ratio:", font=self.arr18).grid(row=0, column=0, sticky="e")
        gear_entry = tk.Entry(win, font=self.arr18)
        gear_entry.insert(0, str(motor["gear_ratio"]))
        gear_entry.grid(row=0, column=1, pady=2)

        tk.Label(win, text="Full Step Angle:", font=self.arr18).grid(row=1, column=0, sticky="e")
        step_entry = tk.Entry(win, font=self.arr18)
        step_entry.insert(0, str(motor["full_step_angle"]))
        step_entry.grid(row=1, column=1, pady=2)

        tk.Label(win, text="Half Step (0 or 1):", font=self.arr18).grid(row=2, column=0, sticky="e")
        half_entry = tk.Entry(win, font=self.arr18)
        half_entry.insert(0, str(int(motor["half_step"])))
        half_entry.grid(row=2, column=1, pady=2)

        def send_config():
            try:
                g = float(gear_entry.get())
                s = float(step_entry.get())
                h = int(half_entry.get())
                if self.arduino_connected:
                    cmd = f"WRITE {motor_id} {g} {s} {h}\n"
                    self.arduino.write(cmd.encode())
                    self.arduino.flush()
                    motor["gear_ratio"] = g
                    motor["full_step_angle"] = s
                    motor["half_step"] = bool(h)
                    self.update_step_params(motor_id)
            except Exception as e:
                print(f"Invalid config: {e}")

        tk.Button(win, text="Save Config", command=send_config, font=self.arr18).grid(row=3, column=0, columnspan=2, pady=5)

    def open_config_pwm(self):
        win = tk.Toplevel(self.root)
        win.title("PWM - Config & Control")

        # Motor control section
        #control_frame = tk.LabelFrame(win, text="Flip Motor Control", font=self.arr18, padx=10, pady=10)
        control_frame = tk.LabelFrame(win, font=self.arr18, padx=10, pady=10)
        control_frame.grid(row=4, column=0, columnspan=2, pady=10, sticky="ew")

        # Config fields
        tk.Label(win, text="Frequency (Hz):", font=self.arr18).grid(row=0, column=0, sticky="e")
        freq_entry = tk.Entry(win, font=self.arr18)
        freq_entry.insert(0, str(self.pwm_freq))
        freq_entry.grid(row=0, column=1, pady=2)

        tk.Label(win, text="Resolution (Bit):", font=self.arr18).grid(row=1, column=0, sticky="e")
        res_entry = tk.Entry(win, font=self.arr18)
        res_entry.insert(0, str(self.pwm_res))
        res_entry.grid(row=1, column=1, pady=2)

        tk.Label(win, text="Duty Cycle:", font=self.arr18).grid(row=2, column=0, sticky="e")
        d_entry = tk.Entry(win, font=self.arr18)
        d_entry.insert(0, f"{self.pwm_d:.2f}")
        d_entry.grid(row=2, column=1, pady=2)

        tk.Label(win, text="Duty Cycle Min:", font=self.arr18).grid(row=3, column=0, sticky="e")
        dmin_entry = tk.Entry(win, font=self.arr18)
        dmin_entry.insert(0, str(self.pwm_dmin))
        dmin_entry.grid(row=3, column=1, pady=2)

        tk.Label(win, text="Duty Cycle Max:", font=self.arr18).grid(row=4, column=0, sticky="e")
        dmax_entry = tk.Entry(win, font=self.arr18)
        dmax_entry.insert(0, str(self.pwm_dmax))
        dmax_entry.grid(row=4, column=1, pady=2)

        def send_pwm_config():
            try:
                f = int(freq_entry.get())
                r = int(res_entry.get())
                d = float(d_entry.get())
                dmin = int(dmin_entry.get())
                dmax = int(dmax_entry.get())
                if self.arduino_connected:
                    cmd = f"PWM SET {d} {f} {r} {dmin} {dmax}\n"
                    self.arduino.write(cmd.encode())
                    self.arduino.flush()                
                self.pwm_freq = f
                self.pwm_res = r
                self.pwm_d = d
                self.pwm_dmin = dmin
                self.pwm_dmax = dmax
            except Exception as e:
                print(f"Invalid config: {e}")

        tk.Button(win, text="Set", command=send_pwm_config, font=self.arr18).grid(row=5, column=0, columnspan=2, pady=5)

    # ---- Flip Motor convenience toggle (0/180) ----
    def flip_180(self):
        cur_angle = self.step_to_angle(1)
        self.go_to_angle(motor_id=motor_id, flip=True, angle = 180.0-cur_angle)

    # ---- Flip Motor convenience toggle (0/120) ----
    def flip_120(self, motor_id):
        cur_angle = self.step_to_angle(motor_id)
        self.go_to_angle(motor_id=motor_id, flip=True, angle = 120.0-cur_angle)

    # ---- Flip Motor convenience toggle (0/120) ----
    def flip_angle(self, motor_id,ang):
        cur_angle = self.step_to_angle(motor_id)
        self.go_to_angle(motor_id=motor_id, flip=True, angle = ang-cur_angle)

    def read_pm16_data(self):
        power = c_double()
        
        while self.pm16_connected and self.pm16_thread_running:
            try:
                self.tlPM.measPower(byref(power),TLPM_DEFAULT_CHANNEL)
                self.pm16_power.set(self.format_output(power.value))
                time.sleep(0.2)

            except CommunicationError:
                return

    # -------- Helpers --------
    def update_step_params(self, motor_id):
        m = self.motors[motor_id]
        steps_per_rev = int((360.0 / (m["full_step_angle"] / (2 if m["half_step"] else 1))) * m["gear_ratio"])
        m["steps_per_rev"] = steps_per_rev
        m["step_angle"] = 360.0 / steps_per_rev

    def step_to_angle(self, motor_id):
        return (self.motors[motor_id]["current_position_steps"] % self.motors[motor_id]["steps_per_rev"]) * self.motors[motor_id]["step_angle"]

    def get_step_angle(self, motor_id):
        return self.motors[motor_id]["step_angle"]

    def get_steps_per_rev(self, motor_id):
        return self.motors[motor_id]["steps_per_rev"]

    def map_speed(self, percent, lower, upper):
        #speed = float(10000.0 - (percent * 9999.0 / 100.0))
        speed = float(lower + (percent * (upper - lower) / 100.0))
        return int(speed)

    def move_xyz(self, direction, event=None):
        ag_uc2_voltage = self.map_speed(self.ag_uc2_speed_var.get(),self.ag_uc2_voltage_lower,self.ag_uc2_voltage_upper)
        ag_uc2_step = self.map_speed(self.ag_uc2_speed_var.get(),self.ag_uc2_step_lower,self.ag_uc2_step_upper)
        self.kim001_step = self.map_speed(self.kim001_speed_var.get(),self.kim001_step_lower,self.kim001_step_upper)

        if direction == "Y+":
            self.piezo.set_step_amplitude_positive(1,ag_uc2_voltage)
            self.piezo.relative_move(1,ag_uc2_step)            
        elif direction == "Y-":
            self.piezo.set_step_amplitude_negative(1,ag_uc2_voltage)
            self.piezo.relative_move(1,-1*ag_uc2_step)  
        elif direction == "X-":
            self.piezo.set_step_amplitude_negative(2,ag_uc2_voltage)
            self.piezo.relative_move(2,-1*ag_uc2_step)  
        elif direction == "X+":
            self.piezo.set_step_amplitude_positive(2,ag_uc2_voltage)
            self.piezo.relative_move(2,ag_uc2_step)  
        elif direction == "STOPXY":
            self.piezo.stop_motion(1)
            self.piezo.stop_motion(2)
        elif direction == "Z+":
            new_pos = self.kim001_step
            self.kim001.move_relative(new_pos)
        elif direction == "Z-":
            new_pos = -1*self.kim001_step
            self.kim001.move_relative(new_pos)
        else:
            print(f"Moving {direction}")

    def format_output(self, input_value):
        if 1e-15 < abs(input_value) <= 1e-12:
            return f"{self.display_digits(input_value*1e15)}f"
        elif 1e-12 < abs(input_value) <= 1e-9:
            return f"{self.display_digits(input_value*1e12)}p"
        elif 1e-9 < abs(input_value) <= 1e-6:
            return f"{self.display_digits(input_value*1e9)}n"
        elif 1e-6 < abs(input_value) <= 1e-3:
            return f"{self.display_digits(input_value*1e6)}u"
        elif 1e-3 < abs(input_value) <= 1:
            return f"{self.display_digits(input_value*1e3)}m"
        elif 1 < abs(input_value) <= 1e3:
            return f"{self.display_digits(input_value)}"
        elif 1e3 < abs(input_value) <= 1e6:
            return f"{self.display_digits(input_value/1e3)}K"
        elif 1e6 < abs(input_value) <= 1e9:
            return f"{self.display_digits(input_value/1e6)}M"
        else:
            return f"{input_value:.2e}"  # For other ranges, use scientific notation

    def display_digits(self, input_value, digits = 4):        
        if input_value < 1:
            return f"{input_value:.4f}"
        elif 1 <= input_value < 10:
            return f"{input_value:.3f}"
        elif 10 <= input_value < 100:
            return f"{input_value:.2f}"
        elif 100 <= input_value < 1000:
            return f"{input_value:.1f}"
        else:
            return f"{input_value:.0f}"

    def pm16_wavelength_value_entered(self, event):
        try:
            new_value = float(self.pm16_wavelength.get())  # Get the new value from the entry
            if self.pm16_connected:
                self.tlPM.setWavelength(c_double(new_value),TLPM_DEFAULT_CHANNEL)
        except ValueError:
            print("Invalid input for limit Ie value. Please enter a valid number.")
            
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Dual Motor Control")
    app = NDFilterGUI(root)
    root.mainloop()
