import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import math
import serial
import time
import serial.tools.list_ports

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
        if angle_deg < self.left_angle:
            angle = angle_deg
        elif angle_deg > self.right_angle:
            angle = angle_deg

        # Check if movement would cross forbidden arc
        def crosses_forbidden(start, end, ccw=True):
            """Return True if arc from start→end CCW crosses forbidden zone."""
            if start > self.right_angle:
                s = start - 360
            else:
                s = start  
            if end > self.right_angle:
                e = end - 360
            else:
                e = end

            if e > s:
                return 0
            elif e < s:
                return 1

        force_direction = crosses_forbidden(self.current_angle, angle_deg)  

        # Update pointer
        self.draw_pointer(angle)

        # Callback to motor
        if self.angle_callback:
            self.angle_callback(angle, force_direction)

class NDFilterGUI:
    def __init__(self, parent_frame):
        self.root = parent_frame
        self.arr18 = ('Arial', 18)

        self.baud_rate = 115200

        # Each motor will have its own parameters
        self.motors = {}
        for motor_id in range(4):
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

        self.arduino = None
        self.connected = False

        self.build_ui()

    # -------- UI --------
    def build_ui(self):
        # Serial Port Selection
        self.port_label = tk.Label(self.root, text="COM Port", font=self.arr18)
        self.port_label.grid(row=0, column=0, padx=5, pady=5)

        self.port_var = tk.StringVar()
        self.port_combobox = ttk.Combobox(self.root, textvariable=self.port_var, width=10, font=self.arr18)
        self.port_combobox.grid(row=0, column=1, padx=5, pady=5)
        self.port_combobox.bind("<Button-1>", self.update_ports)

        self.connect_button = tk.Button(self.root, text="Connect", command=self.connect_arduino,
                                        font=self.arr18, bg="red", fg="white")
        self.connect_button.grid(row=0, column=2, padx=5, pady=5)

        # NDF Filter
        self.config_button1 = tk.Button(self.root, text="Config & Ctrl NDF", command=lambda: self.open_config_control(0), font=self.arr18)
        self.config_button1.grid(row=0, column=3, padx=5)
        self.config_button1.config(state='disabled')

        # Laser Flip
        self.config_button2 = tk.Button(self.root, text="Config & Ctrl LSFP", command=lambda: self.open_config_control(1), font=self.arr18)
        self.config_button2.grid(row=0, column=4, padx=5)
        self.config_button2.config(state='disabled')

        self.flip_button1 = tk.Button(self.root, text="LS Flip", command=lambda: self.flip_120(motor_id=1), font=self.arr18)
        self.flip_button1.grid(row=0, column=5, padx=5, pady=5)
        self.flip_button1.config(state='disabled')

        # BS Flip
        self.config_button3 = tk.Button(self.root, text="Config & Ctrl BSFP", command=lambda: self.open_config_control(2), font=self.arr18)
        self.config_button3.grid(row=1, column=4, padx=5)
        self.config_button3.config(state='disabled')

        self.flip_button2 = tk.Button(self.root, text="BS Flip", command=lambda: self.flip_120(motor_id=2), font=self.arr18)
        self.flip_button2.grid(row=1, column=5, padx=5, pady=5)
        self.flip_button2.config(state='disabled')

        self.motors[1]["flip_button"] = self.flip_button1
        self.motors[2]["flip_button"] = self.flip_button2

        # Light adjuster
        self.config_button4 = tk.Button(self.root, text="Config & Ctrl LGT", command=lambda: self.open_config_control(3), font=self.arr18)
        self.config_button4.grid(row=1, column=3, padx=5)
        self.config_button4.config(state='disabled')

        # ND Filter Wheel Go-to angle
        self.build_motor_controls(self.root, 0, goto=1, row_start=2)

        # ND Filter Wheel visualization
        self.wheel_canvas = FilterWheelCanvas(self.root, image_path="ND1.png", size=350)
        self.wheel_canvas.grid(row=5, column=0, columnspan=3, pady=20)
        self.wheel_canvas.angle_callback = self.on_wheel_click
        self.wheel_canvas.grid(row=5, column=0, columnspan=3, pady=20)
        self.wheel_canvas.angle_callback = self.on_wheel_click

        # Connect canvas clicks to motor control
        self.dial_label = tk.Label(self.root, text="White Light Dial", font=self.arr18)
        self.dial_label.grid(row=4, column=3, columnspan=3, pady=(0,0))
        self.dial_canvas = DialCanvas(self.root, size=300)
        self.dial_canvas.grid(row=5, column=3, columnspan=3, pady=(20,0), sticky="n")
        self.dial_canvas.angle_callback = self.on_dial_click   

    def build_motor_controls(self, parent, motor_id, goto=0, row_start=0):
        motor = self.motors[motor_id]

        if goto == 0:
            # Speed Slider and Entry
            speed_label = tk.Label(parent, text=f"Speed (%)", font=self.arr18).grid(row=row_start, column=0, padx=5, pady=5)
            speed_slider = tk.Scale(parent, from_=0.0, to=100.0, orient=tk.HORIZONTAL,
                                    resolution=0.01, font=self.arr18, length=250, variable=motor["speed_var"], showvalue=0)
            speed_slider.set(100)
            speed_slider.grid(row=row_start, column=1, columnspan=2, padx=5, pady=5)
            motor["speed_slider"] = speed_slider

            speed_entry = tk.Entry(parent, textvariable=motor["speed_var"], font=self.arr18, width=6)
            speed_entry.grid(row=row_start, column=3, padx=5, pady=5)
            speed_entry.bind("<Return>", lambda e: self.on_speed_entry_change(motor_id))
            speed_entry.bind("<FocusOut>", lambda e: self.on_speed_entry_change(motor_id))
            motor["speed_entry"] = speed_entry

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
        goto_entry = tk.Entry(parent, textvariable=motor["goto_angle_var"], font=self.arr18, width=8)
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
 
    def on_wheel_click(self, angle_deg):
        """Handle user clicking on wheel → move motor to that angle."""
        self.motors[0]["goto_angle_var"].set(f"{(angle_deg%360):.1f}")
        self.go_to_angle(0)  # move motor 0

    def on_dial_click(self, angle_deg, force_direction=None):
        """Move motor according to dial click (only within arc)."""
        self.motors[3]["goto_angle_var"].set(f"{(angle_deg % 360):.1f}")
        self.go_to_angle(3, angle=angle_deg, force_direction=force_direction)

    def update_ports(self, event=None):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combobox["values"] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    def connect_arduino(self):
        motor = self.motors[0]
        if not self.connected:
            port = self.port_var.get()
            if not port:
                print("No serial port selected!")
                return
            try:
                self.arduino = serial.Serial(port, self.baud_rate, timeout=1, write_timeout=1)
                self.connected = True
                self.connect_button.config(text="Connected", bg="green")
                self.config_button1.config(state="normal")
                self.config_button2.config(state="normal")
                self.config_button3.config(state="normal")
                self.config_button4.config(state="normal")
                self.flip_button1.config(state='normal')
                self.flip_button2.config(state='normal')
                #for key in ["goto_button", "zero_button", "toggle_button"]:
                for key in ["goto_button"]:
                    if key in motor:  # only touch if it exists
                        motor[key].config(state="normal")

                # Read config for both motors
                for motor_id in self.motors.keys():
                    self.request_config(motor_id)
                    cur_angle = self.step_to_angle(motor_id)
                    self.motors[motor_id]["goto_angle_var"].set(f"{(cur_angle%360):.1f}")
                    if motor_id == 0:
                        self.wheel_canvas.update_angle(self.step_to_angle(0))
                    elif motor_id == 1:
                        if cur_angle == 0:
                            self.flip_button1.config(text="Flip Up", bg="green")
                        else:
                            self.flip_button1.config(text="Flip Down", bg="red")
                    elif motor_id == 2:
                        if cur_angle == 0:
                            self.flip_button2.config(text="Flip Up", bg="green")
                        else:
                            self.flip_button2.config(text="Flip Down", bg="red")
                    elif motor_id == 3:
                        self.dial_canvas.draw_pointer(self.step_to_angle(3))
                        
            except serial.SerialException as e:
                print(f"SerialException: {e}")
        else:
            if self.arduino and self.arduino.is_open:
                try:
                    self.arduino.close()
                    #print("Serial port closed.")
                except Exception as e:
                    print(f"Error closing serial port: {e}")
            self.arduino = None
            self.connected = False
            self.connect_button.config(text="Disconnected", bg="red")
            self.config_button1.config(state="disabled")
            self.config_button2.config(state="disabled")
            self.config_button3.config(state="disabled")
            self.config_button4.config(state="disabled")
            self.flip_button1.config(state='disabled')
            self.flip_button2.config(state='disabled')

            for key in ["goto_button", "zero_button", "toggle_button"]:
                if key in motor:
                    motor[key].config(state="disabled")

    def request_config(self, motor_id):
        if self.connected:
            cmd = f"READ {motor_id}\n"
            self.arduino.write(cmd.encode())
            self.arduino.flush()
            response = self.arduino.readline().decode().strip()
            try:
                parts = response.split(',')
                self.motors[motor_id]["gear_ratio"] = float(parts[0])
                self.motors[motor_id]["full_step_angle"] = float(parts[1])
                self.motors[motor_id]["half_step"] = bool(int(parts[2]))
                self.motors[motor_id]["current_position_steps"] = int(parts[3])
                self.update_step_params(motor_id)
            except Exception as e:
                print(f"Invalid config for motor {motor_id}: {response}")

    def on_speed_entry_change(self, motor_id, event=None):
        motor = self.motors[motor_id]
        try:
            val = float(motor["speed_var"].get())
            if 0.0 <= val <= 100.0:
                motor["speed_slider"].set(val)  # Sync slider
                #self.send_motor_command()
            else:
                print("Error: Speed must be between 0.00% and 100.00%")
        except ValueError:
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
        if self.connected and self.arduino:
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
                speed = self.map_speed(motor["speed_var"].get())
                command = f"SET {motor_id} {speed} {direction} {steps_to_move}\n"
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
                        time.sleep(0.05)  # Avoid CPU spin

                motor["current_position_steps"] = target_steps
                if motor_id == 0:
                    self.wheel_canvas.update_angle(self.step_to_angle(0))

                if flip == True:
                    flip_btn = motor.get("flip_button")
                    if flip_btn and flip_btn.winfo_exists():
                        if self.step_to_angle(motor_id) == 0:
                            flip_btn.config(text="Flip Up", bg="green")
                        else:
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
        if self.connected:
            cmd = f"ZERO {motor_id}\n"
            self.arduino.write(cmd.encode())
            self.arduino.flush()

    def toggle_motor(self, motor_id):
        motor = self.motors[motor_id]
        if self.arduino and self.arduino.is_open:
            if not motor["motor_running"]:
                try:
                    speed = self.map_speed(motor["speed_var"].get())
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
                if self.connected:
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

    # ---- Flip Motor convenience toggle (0/180) ----
    def flip_180(self):
        cur_angle = self.step_to_angle(1)
        self.go_to_angle(motor_id=motor_id, flip=True, angle = 180.0-cur_angle)

    # ---- Flip Motor convenience toggle (0/120) ----
    def flip_120(self, motor_id):
        cur_angle = self.step_to_angle(motor_id)
        self.go_to_angle(motor_id=motor_id, flip=True, angle = 120.0-cur_angle)

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

    def map_speed(self, percent):
        speed = float(10000.0 - (percent * 9999.0 / 100.0))
        return round(speed)

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Dual Motor Control")
    app = NDFilterGUI(root)
    root.mainloop()
