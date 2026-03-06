#include <EEPROM.h>
#include "esp_system.h"
#include <math.h>  // for lround()

// Motor 0 pins
#define M0_IN1 7
#define M0_IN2 6
#define M0_IN3 4
#define M0_IN4 3
#define M0_NSLEEP_PIN 5

// Motor 1 pins
#define M1_IN1  20
#define M1_IN2  10
#define M1_IN3  0
#define M1_IN4  1
#define M1_NSLEEP_PIN 2

// PWM pins
#define PWM_OUT 21

const int MOTOR_NUMBER = 2;
const int EEPROM_SIZE = 2048;
const int BAUD_RATE = 115200;

struct Config {
  uint32_t signature;  // magic number to detect validity
  float gear_ratio;
  float full_step_angle;
  bool half_step;
  long current_position;
  uint8_t last_step_index;
};

struct Motor {
  // Pins
  int in1, in2, in3, in4, nsleep;
  // Runtime vars
  int step_speed;
  int direction;
  bool running;
  bool infinite_mode;
  long steps_remaining;
  int step_index;
  long current_position_steps;
  // Config
  float gear_ratio;
  float full_step_angle;
  bool half_step;
  // Timing
  unsigned long last_step_time;
};

Motor motors[MOTOR_NUMBER];

struct ConfigPWM {
  uint32_t signature;
  int pwm_freq;
  int pwm_res;
  float pwm_d;
  int pwm_dmin;
  int pwm_dmax;
};

ConfigPWM pwm;

const int EEPROM_ADDR[3] = {
  0,
  sizeof(Config),
  2 * sizeof(Config)
};

const uint32_t MOTOR_CFG_SIG  = 0xDEADBEEF;
const uint32_t PWM_CFG_SIG    = 0xBEEFDEAD;

// 8-step half-stepping sequence
const int step_sequence_8[8][4] = {
  {1, 0, 0, 0},
  {1, 0, 1, 0},
  {0, 0, 1, 0},
  {0, 1, 1, 0},
  {0, 1, 0, 0},
  {0, 1, 0, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1}
};

const int step_sequence_4[4][4] = {
  {1,0,1,0},
  {0,1,1,0},
  {0,1,0,1},
  {1,0,0,1}
};


// ---------------- Function prototypes ----------------
void setupMotor(int id, int in1, int in2, int in3, int in4, int nsleep);
void setupPWM(int pwmPin);
void loadConfig(int id);
void saveConfig(int id);
void loadConfigPWM();
void saveConfigPWM();
long stepsPerRev(int id);
void stepMotor(int id);
void stopMotor(int id);

void setup() {
	Serial.begin(BAUD_RATE);
	EEPROM.begin(EEPROM_SIZE);
	setupMotor(0, M0_IN1, M0_IN2, M0_IN3, M0_IN4, M0_NSLEEP_PIN);
	setupMotor(1, M1_IN1, M1_IN2, M1_IN3, M1_IN4, M1_NSLEEP_PIN);
	setupPWM(PWM_OUT);
}

void loop() {
	// ----------- Serial Command Handling -----------
	if (Serial.available()) {
		String command = Serial.readStringUntil('\n');
		command.trim();

		if (command.startsWith("SET")) {
			// SET <id> <speed> <dir> [steps]
			int id, speed, dir, steps;
			int args = sscanf(command.c_str(), "SET %d %d %d %d", &id, &speed, &dir, &steps);
			if (id >= 0 && id < MOTOR_NUMBER) {
				motors[id].step_speed = constrain(speed, 1, 10000);
				motors[id].direction = (dir == 0) ? 1 : -1;
				digitalWrite(motors[id].nsleep, HIGH);
				if (args == 4) {
					motors[id].steps_remaining = steps;
					motors[id].infinite_mode = false;
					motors[id].running = true;
				} else {
					motors[id].infinite_mode = true;
				}
			}

		} else if (command.startsWith("START")) {
			int id;
			if (sscanf(command.c_str(), "START %d", &id) == 1 && id >= 0 && id < MOTOR_NUMBER) {
				digitalWrite(motors[id].nsleep, HIGH);
				motors[id].running = true;
			}

		} else if (command.startsWith("STOP")) {
			int id;
			if (sscanf(command.c_str(), "STOP %d", &id) == 1 && id >= 0 && id < MOTOR_NUMBER) {
				motors[id].running = false;
				stopMotor(id);
			}

		} else if (command.startsWith("READ")) {
			int id;
			if (sscanf(command.c_str(), "READ %d", &id) == 1 && id >= 0 && id < MOTOR_NUMBER) {
				loadConfig(id);
				Serial.print(motors[id].gear_ratio);
				Serial.print(",");
				Serial.print(motors[id].full_step_angle);
				Serial.print(",");
				Serial.print(motors[id].half_step ? 1 : 0);
				Serial.print(",");
				Serial.println(motors[id].current_position_steps);
			}

		} else if (command.startsWith("WRITE")) {
			int id, h;
			float g, s;
			if (sscanf(command.c_str(), "WRITE %d %f %f %d", &id, &g, &s, &h) == 4 && id >= 0 && id < MOTOR_NUMBER) {
				motors[id].gear_ratio = g;
				motors[id].full_step_angle = s;
				motors[id].half_step = (h > 0);
				saveConfig(id);
			}

		} else if (command.startsWith("ZERO")) {
			int id;
			if (sscanf(command.c_str(), "ZERO %d", &id) == 1 && id >= 0 && id < MOTOR_NUMBER) {
				motors[id].current_position_steps = 0;
				saveConfig(id);
			}

		} else if (command.startsWith("ID")) {
			Serial.println("STEPPER");

		} else if (command.startsWith("PWM")) {
			if (command.startsWith("PWM SET")) {
				float d;
				int f, r, dmin, dmax;
				int pwmValue;
				if(sscanf(command.c_str(), "PWM SET %f %d %d %d %d", &d, &f, &r, &dmin, &dmax)  == 5) {
					pwm.pwm_freq = f;
					pwm.pwm_res = r;
					pwm.pwm_dmin = dmin;
					pwm.pwm_dmax = dmax;
					pwm.pwm_d = d;
					pwmValue = (d / 100.0) * 100;
					ledcAttach(PWM_OUT, pwm.pwm_freq, pwm.pwm_res);
					ledcWrite(PWM_OUT, pwmValue);
					saveConfigPWM();
				}

				// Always update duty cycle if present
				else if (sscanf(command.c_str(), "PWM SET %f", &d) == 1) {
					pwm.pwm_d = d;
					pwmValue = (d / 100.0) * 100;
					ledcAttach(PWM_OUT, pwm.pwm_freq, pwm.pwm_res);
					ledcWrite(PWM_OUT, pwmValue);
					saveConfigPWM();
				}
			} else if (command.startsWith("PWM GET")) {
				loadConfigPWM();
				Serial.print(pwm.pwm_d);
				Serial.print(",");
				Serial.print(pwm.pwm_freq);
				Serial.print(",");
				Serial.print(pwm.pwm_res);
				Serial.print(",");
				Serial.print(pwm.pwm_dmin);
				Serial.print(",");
				Serial.println(pwm.pwm_dmax);
			}
		}
	}

	// ----------- Motor Stepping -----------
	for (int id = 0; id < MOTOR_NUMBER; id++) {
		if (motors[id].running && millis() - motors[id].last_step_time >= motors[id].step_speed) {
			stepMotor(id);
			motors[id].last_step_time = millis();

			if (!motors[id].infinite_mode) {
				motors[id].steps_remaining--;
				if (motors[id].steps_remaining <= 0) {
					motors[id].running = false;
					motors[id].infinite_mode = true;
					stopMotor(id);
					Serial.print("DONE ");
					Serial.print(id);
					Serial.print(" ");
					Serial.println(motors[id].current_position_steps);
				}
			}
		}
	}
}

// ---------------- Function Definitions ----------------
void setupMotor(int id, int in1, int in2, int in3, int in4, int nsleep) {
	motors[id].in1 = in1;
	motors[id].in2 = in2;
	motors[id].in3 = in3;
	motors[id].in4 = in4;
	motors[id].nsleep = nsleep;

	pinMode(in1, OUTPUT);
	pinMode(in2, OUTPUT);
	pinMode(in3, OUTPUT);
	pinMode(in4, OUTPUT);
	pinMode(nsleep, OUTPUT);

	digitalWrite(in1, LOW);
	digitalWrite(in2, LOW);
	digitalWrite(in3, LOW);
	digitalWrite(in4, LOW);
	digitalWrite(nsleep, LOW);

	motors[id].step_speed = 500;
	motors[id].direction = 1;
	motors[id].running = false;
	motors[id].infinite_mode = false;
	motors[id].steps_remaining = 0;
	motors[id].step_index = 0;
	motors[id].current_position_steps = 0;
	motors[id].last_step_time = 0;

	loadConfig(id);
}

void setupPWM(int pwmPin) {
	pinMode(pwmPin, OUTPUT);
	digitalWrite(pwmPin, LOW);

	ledcAttach(pwmPin, 10, 8);
	ledcWrite(pwmPin, 0);

	loadConfigPWM();
}

void loadConfig(int id) {
	Config cfg;
	EEPROM.get(EEPROM_ADDR[id], cfg);
	if (cfg.signature != MOTOR_CFG_SIG) {
		motors[id].gear_ratio = 100.0;
		motors[id].full_step_angle = 18.0;
		motors[id].half_step = true;
		motors[id].current_position_steps = 0;
		saveConfig(id);
	} else {
		motors[id].gear_ratio = cfg.gear_ratio;
		motors[id].full_step_angle = cfg.full_step_angle;
		motors[id].half_step = cfg.half_step;
		motors[id].current_position_steps = cfg.current_position;
	}
}

void saveConfig(int id) {
	Config cfg = {MOTOR_CFG_SIG, motors[id].gear_ratio, motors[id].full_step_angle,
				motors[id].half_step, motors[id].current_position_steps};
	EEPROM.put(EEPROM_ADDR[id], cfg);
	EEPROM.commit();
}

void loadConfigPWM() {
	ConfigPWM cfg;
	EEPROM.get(EEPROM_ADDR[2], cfg);
	if (cfg.signature != PWM_CFG_SIG) {
		pwm.pwm_freq = 50000;
		pwm.pwm_res = 8;
		pwm.pwm_dmin = 0;
		pwm.pwm_d = 0.0;
		pwm.pwm_dmax = 5;
		saveConfigPWM();
	} else {
		pwm.pwm_freq = cfg.pwm_freq;
		pwm.pwm_res = cfg.pwm_res;
		pwm.pwm_dmin = cfg.pwm_dmin;
		pwm.pwm_d = cfg.pwm_d;
		pwm.pwm_dmax = cfg.pwm_dmax;
	}
}

void saveConfigPWM() {
	ConfigPWM cfg = {PWM_CFG_SIG, pwm.pwm_freq, pwm.pwm_res, pwm.pwm_d, pwm.pwm_dmin, pwm.pwm_dmax};
	EEPROM.put(EEPROM_ADDR[2], cfg);
	EEPROM.commit();
}

long stepsPerRev(int id) {
	float step_angle = motors[id].full_step_angle / (motors[id].half_step ? 2.0 : 1.0);
	return lround((360.0 / step_angle) * motors[id].gear_ratio);
	//float step_angle = motors[id].full_step_angle; // no /2 for half-step
	//return lround((360.0 / step_angle) * motors[id].gear_ratio);
}

void stepMotor(int id) {
	if(motors[id].half_step){
		motors[id].step_index = (motors[id].step_index + motors[id].direction + 8) % 8;
		digitalWrite(motors[id].in1, step_sequence_8[motors[id].step_index][0]);
		digitalWrite(motors[id].in2, step_sequence_8[motors[id].step_index][1]);
		digitalWrite(motors[id].in3, step_sequence_8[motors[id].step_index][2]);
		digitalWrite(motors[id].in4, step_sequence_8[motors[id].step_index][3]);
	}
	else {
		motors[id].step_index = (motors[id].step_index + motors[id].direction + 4) % 4;
		digitalWrite(motors[id].in1, step_sequence_4[motors[id].step_index][0]);
		digitalWrite(motors[id].in2, step_sequence_4[motors[id].step_index][1]);
		digitalWrite(motors[id].in3, step_sequence_4[motors[id].step_index][2]);
		digitalWrite(motors[id].in4, step_sequence_4[motors[id].step_index][3]);
	}
	motors[id].current_position_steps =
	  (motors[id].current_position_steps + motors[id].direction + stepsPerRev(id)) % stepsPerRev(id);
}

void stopMotor(int id) {
	digitalWrite(motors[id].nsleep, LOW);
	digitalWrite(motors[id].in1, LOW);
	digitalWrite(motors[id].in2, LOW);
	digitalWrite(motors[id].in3, LOW);
	digitalWrite(motors[id].in4, LOW);
	saveConfig(id);
}
