// ===== 8-PIN MOTOR TEST (4x Motors) =====

struct Motor {
  const char* name;
  int rpwm;
  int lpwm;
};

Motor motors[] = {
  {"L-1", 19, 20},
  {"L-2", 47, 48},
  {"R-2", 11, 12},  // note: R-2 before R-1
  {"R-1",  9, 10}
};

const int freq = 1000;
const int resolution = 8;

void setup() {
  Serial.begin(115200);

  for (auto &m : motors) {
    ledcAttach(m.rpwm, freq, resolution);
    ledcAttach(m.lpwm, freq, resolution);
    pinMode(m.rpwm, OUTPUT);
    pinMode(m.lpwm, OUTPUT);
  }

  Serial.println("8-Pin Motor Test Start");
}

void testPin(int pin, const char* motorName, const char* pinName) {
  Serial.print("Testing ");
  Serial.print(motorName);
  Serial.print(" ");
  Serial.print(pinName);
  Serial.print(" (Pin ");
  Serial.print(pin);
  Serial.println(") - ON 1s");

  ledcWrite(pin, 200);   // 78% duty
  delay(1000);
  ledcWrite(pin, 0);
  delay(300);
}

void testMotor(const Motor &m) {
  Serial.print("\n--- Testing ");
  Serial.print(m.name);
  Serial.println(" ---");

  testPin(m.rpwm, m.name, "RPWM");
  testPin(m.lpwm, m.name, "LPWM");
}

void runMotor(const Motor &m, int speed, const char* dir) {
  Serial.print(m.name);
  Serial.print(" ");
  Serial.println(dir);

  if (speed >= 0) {
    ledcWrite(m.rpwm, speed);
    ledcWrite(m.lpwm, 0);
  } else {
    ledcWrite(m.rpwm, 0);
    ledcWrite(m.lpwm, -speed);
  }
}

void stopMotor(const Motor &m) {
  ledcWrite(m.rpwm, 0);
  ledcWrite(m.lpwm, 0);
}

void stopAll() {
  for (auto &m : motors) stopMotor(m);
}

void loop() {
  // ===== PHASE 1: Individual Pin Test =====
  Serial.println("\n========== PIN TEST ==========");
  for (auto &m : motors) testMotor(m);
  Serial.println("\nAll pins tested.");

  delay(2000);

  // ===== PHASE 2: Direction Test (one motor at a time) =====
  Serial.println("\n========== DIRECTION TEST ==========");

  for (auto &m : motors) {
    runMotor(m, 150, "FORWARD");
    delay(2000);
    runMotor(m, 0, "STOP");
    delay(500);
    runMotor(m, -150, "REVERSE");
    delay(2000);
    stopMotor(m);
    Serial.print(m.name);
    Serial.println(" DONE\n");
    delay(1000);
  }

  // ===== PHASE 3: All Forward / All Reverse =====
  Serial.println("\n========== ALL MOTORS ==========");

  Serial.println("ALL FORWARD");
  for (auto &m : motors) runMotor(m, 150, "");
  delay(3000);

  Serial.println("ALL STOP");
  stopAll();
  delay(1000);

  Serial.println("ALL REVERSE");
  for (auto &m : motors) runMotor(m, -150, "");
  delay(3000);

  Serial.println("ALL STOP");
  stopAll();

  Serial.println("\n========== TEST COMPLETE ==========\n");
  delay(5000);
}