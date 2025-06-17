import tkinter as tk
from tkinter import ttk, messagebox
import serial
import time
import serial.tools.list_ports

class NDFilterGUI:
    def __init__(self, parent_frame):
        self.root = parent_frame
        self.arr18 = ('Arial',18)

        self.baud_rate = 115200

        # Stepper motor configuration
        self.gear_ratio = 100  # Gearbox ratio (1)
        self.full_step_angle = 18.00  # Step angle of motor in degrees
        self.half_step = True  # Using half-step mode
        self.current_position_steps = 0  # Tracks current position in steps
        self.goto_angle_var = tk.StringVar(value="0.0")

        self.update_step_params()
        
        self.arduino = None
        self.motor_running = False
        self.connected = False
        self.speed_var = tk.DoubleVar(value=100)
        self.direction = 0  # Default direction
        
        self.build_ui()

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
        self.config_button = tk.Button(self.root, text="Configure", command=self.open_config_window, font=self.arr18)
        self.config_button.grid(row=0, column=3, padx=5)
        self.config_button.config(state='disabled')

        # Speed Slider
        self.speed_label = tk.Label(self.root, text="Speed (%)", font=self.arr18)
        self.speed_label.grid(row=1, column=0, padx=5, pady=5)

        self.speed_slider = tk.Scale(self.root, from_=0.0, to=100.0, orient=tk.HORIZONTAL,
                             resolution=0.01, font=self.arr18, length=250, variable=self.speed_var,
                             command=self.on_slider_change, showvalue=0)
        self.speed_slider.set(100)
        self.speed_slider.grid(row=1, column=1, columnspan=2, padx=5, pady=5)

        self.speed_entry = tk.Entry(self.root, textvariable=self.speed_var, font=self.arr18, width=6)
        self.speed_entry.grid(row=1, column=3, padx=5, pady=5)
        self.speed_entry.bind("<Return>", self.on_speed_entry_change)
        self.speed_entry.bind("<FocusOut>", self.on_speed_entry_change)

        # Direction Buttons
        self.direction = 0  # 0 = Forward, 1 = Backward
        self.dir_button = tk.Button(self.root, text="Forward", font=self.arr18,
                                    command=self.toggle_direction)
        self.dir_button.grid(row=1, column=4, columnspan=2, padx=5, pady=5)

        # Go-to angle input
        self.goto_label = tk.Label(self.root, text="Go To (°)", font=self.arr18)
        self.goto_label.grid(row=3, column=0, padx=5, pady=5)

        self.goto_entry = tk.Entry(self.root, textvariable=self.goto_angle_var, font=self.arr18, width=8)
        self.goto_entry.grid(row=3, column=1, padx=5, pady=5)

        self.goto_button = tk.Button(self.root, text="Move", bg="orange", command=self.go_to_angle, font=self.arr18)
        self.goto_button.grid(row=3, column=2, padx=5, pady=5)
        self.goto_button.config(state='disabled')

        self.zero_button = tk.Button(self.root, text="Zero", command=self.zero_angle, font=self.arr18)
        self.zero_button.grid(row=3, column=3)
        self.zero_button.config(state='disabled')

        # Start/Stop Toggle Button
        self.toggle_button = tk.Button(self.root, text="Start Free Running", command=self.toggle_motor,
                                       font=self.arr18, bg="green", fg="white", width=15, height=2)
        self.toggle_button.grid(row=4, column=1, columnspan=2, pady=10)
        self.toggle_button.config(state='disabled')

    def go_to_angle(self):
        if self.connected and self.arduino:
            try:
                #target_angle = float(self.goto_entry.get()) % 360.00
                target_angle = float(self.goto_angle_var.get().replace(',', '.')) % 360.00
                target_steps = round(target_angle / self.step_angle)
                delta_steps = (target_steps - self.current_position_steps) % self.steps_per_rev

                # Choose shortest direction
                if delta_steps > self.steps_per_rev / 2:
                    direction = 1  # CCW
                    steps_to_move = self.steps_per_rev - delta_steps
                else:
                    direction = 0  # CW
                    steps_to_move = delta_steps

                self.toggle_button.config(state='disabled')
                self.goto_button.config(text="Moving", bg="red")
                self.root.update_idletasks()
                speed = self.map_speed(self.speed_var.get())
                command = f"SET {speed} {direction} {steps_to_move}\n"
                self.arduino.write(command.encode())
                self.arduino.flush()

                deadline = time.time() + 6  # 6-second timeout
                while time.time() < deadline:
                    if self.arduino.in_waiting:
                        response = self.arduino.readline().decode().strip()
                        if response.startswith("DONE"):
                            #print("Response from Arduino:", response)
                            try:
                                _, current_step = response.split()
                                #print(f"Current step count: {int(current_step)}")
                            except ValueError:
                                print("Malformed DONE response:", response)
                            break
                    else:
                        time.sleep(0.05)  # Avoid CPU spin

                self.current_position_steps = target_steps
                #print(f"Software step count: {self.current_position_steps}")
                self.goto_button.config(text="Move", bg="orange")
                self.toggle_button.config(state='normal')
                #print(f"Moved to angle: {target_angle:.2f}°, step_angle: {self.step_angle}, steps: {target_steps}, steps_to_move: {steps_to_move}")

            except ValueError:
                print("Error", "Invalid angle input.")

    def update_ports(self, event=None):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combobox["values"] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    def connect_arduino(self):
        if not self.connected:
            port = self.port_var.get()
            #print(f"Trying to connect to port: {port}")
            if port == "No Ports Found":
                print("Error", "No serial ports detected!")
                return

            try:
                self.arduino = serial.Serial(port, self.baud_rate, timeout=1, write_timeout=1)
                self.connected = True
                self.connect_button.config(text="Connected", bg="green")
                self.config_button.config(state="normal")
                self.goto_button.config(state="normal")
                self.zero_button.config(state='normal')
                self.toggle_button.config(state="normal")
                self.request_config()
                self.goto_angle_var.set(f"{self.step_to_angle():.1f}")

            except serial.SerialException as e:
                print(f"SerialException: {e}")
        else:
            if self.connected and self.arduino and self.arduino.is_open:
                try:
                    self.arduino.close()
                    #print("Serial port closed.")
                except Exception as e:
                    print(f"Error closing serial port: {e}")
            self.arduino = None
            self.connected = False
            self.connect_button.config(text="Disconnected", bg="red")
            self.config_button.config(state="disabled")
            self.goto_button.config(state="disabled")
            self.zero_button.config(state='disabled')
            self.toggle_button.config(state="disabled")

    def update_step_params(self):
        self.steps_per_rev = int((360.0 / (self.full_step_angle / (2 if self.half_step else 1))) * self.gear_ratio)
        self.step_angle = 360.0 / self.steps_per_rev

    def step_to_angle(self):
        return (self.current_position_steps % self.steps_per_rev) * self.step_angle

    def request_config(self):
        if self.connected:
            self.arduino.write(b"READ\n")
            self.arduino.flush()
            response = self.arduino.readline().decode().strip()
            #print(response)
            try:
                parts = response.split(',')
                self.gear_ratio = float(parts[0])
                self.full_step_angle = float(parts[1])
                self.half_step = bool(int(parts[2]))
                self.current_position_steps = int(parts[3])
                self.update_step_params()
                #print("Received config:", parts)
            except Exception as e:
                print(f"Invalid CONFIG? response: {response}")

    def open_config_window(self):
        win = tk.Toplevel(self.root)
        win.title("Configure Stepper")

        tk.Label(win, text="Gear Ratio:", font=self.arr18).grid(row=0, column=0)
        gear_entry = tk.Entry(win, font=self.arr18)
        gear_entry.insert(0, str(self.gear_ratio))
        gear_entry.grid(row=0, column=1)

        tk.Label(win, text="Full Step Angle:", font=self.arr18).grid(row=1, column=0)
        step_entry = tk.Entry(win, font=self.arr18)
        step_entry.insert(0, str(self.full_step_angle))
        step_entry.grid(row=1, column=1)

        tk.Label(win, text="Half Step (0 or 1):", font=self.arr18).grid(row=2, column=0)
        half_entry = tk.Entry(win, font=self.arr18)
        half_entry.insert(0, str(int(self.half_step)))
        half_entry.grid(row=2, column=1)

        def send_config():
            try:
                g = float(gear_entry.get())
                s = float(step_entry.get())
                h = int(half_entry.get())
                if self.connected:
                    cmd = f"WRITE {g} {s} {h}\n"
                    self.arduino.write(cmd.encode())
                    self.arduino.flush()
                    self.gear_ratio = g
                    self.full_step_angle = s
                    self.half_step = bool(h)
                    self.update_step_params()
                    win.destroy()
            except Exception as e:
                print("Error", f"Invalid input: {e}")

        tk.Button(win, text="Save", command=send_config, font=self.arr18).grid(row=3, column=0, columnspan=2, pady=5)

    def zero_angle(self):
        #self.request_config()
        self.current_position_steps = 0
        if self.connected:
            self.arduino.write(b"ZERO\n")
        #print("Position zeroed")

    def on_slider_change(self, value):
        try:
            self.speed_var.set(round(float(value), 2))
            #self.send_motor_command()
        except ValueError:
            pass

    #def on_slider_change(self, value):
    #    self.send_motor_command()

    def on_speed_entry_change(self, event=None):
        try:
            val = float(self.speed_var.get())
            if 0.0 <= val <= 100.0:
                self.speed_slider.set(val)  # Sync slider
                #self.send_motor_command()
            else:
                print("Error: Speed must be between 0.00% and 100.00%")
        except ValueError:
            print("Error: Invalid number for speed.")

    def send_motor_command(self):
        if self.connected and self.arduino and self.arduino.is_open:
            try:
                speed = self.map_speed(float(self.speed_slider.get()))
                direction = self.direction

                command = f"SET {speed} {direction}\n"
                #print(f"Sending: {command.strip()}")
                self.arduino.write(command.encode())
                self.arduino.flush()
            except Exception as e:
                print(f"Error sending command: {e}")
        else:
            print("Arduino not connected.")

    def map_speed(self, percent):
        """Map 0–100% to 2000–1 ms/step (inverse mapping)."""
        speed = float(10000.0 - (percent * 9999.0 / 100.0))
        return round(speed)  # 0% = 2000, 100% = 1
    
    def toggle_direction(self):
        self.direction = 1 - self.direction  # Toggle 0 <-> 1
        dir_text = "Forward" if self.direction == 0 else "Backward"
        self.dir_button.config(text=f"{dir_text}")
        #self.send_motor_command()

    def toggle_motor(self):
        if self.arduino and self.arduino.is_open:
            if not self.motor_running:
                try:                
                    speed = self.map_speed(self.speed_var.get())
                    direction = self.direction
                    command = f"SET {speed} {direction}\n"
                    self.arduino.write(command.encode())
                    self.arduino.flush()
                    self.arduino.write(b"START\n")
                    self.arduino.flush()
                    self.goto_button.config(state="disabled")
                    self.toggle_button.config(text="Running", bg="red")
                    self.motor_running = True
                    #print("Motor started.")
                except Exception as e:
                    print(f"Error starting motor: {e}")
            else:
                try:
                    self.arduino.write(b"STOP\n")
                    self.arduino.flush()
                    self.toggle_button.config(text="Start Free Running", bg="green")
                    self.goto_button.config(state="normal")
                    self.motor_running = False
                    #print("Motor stopped.")
                except Exception as e:
                    print(f"Error stopping motor: {e}")
        else:
            print("Arduino not connected.")

if __name__ == "__main__":
    root = tk.Tk()
    app = NDFilterGUI(root)
    root.mainloop()
