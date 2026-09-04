/*
 * ==========================================================================
 *  OSTEOARTHRITIS MONITORING WEARABLE - ESP32 FIRMWARE
 *  Real-time biomechanical data acquisition & WebSocket streaming
 * ==========================================================================
 *
 *  HARDWARE MAP:
 *  ┌─────────────────────────────────────────────────────────────────┐
 *  │  MPU6050 x4 (via TCA9548A)  → I2C (SDA=21, SCL=22)           │
 *  │  OLED SSD1306               → I2C (same bus, addr 0x3C)       │
 *  │  Flex Sensors x2            → GPIO34 (L Knee), GPIO35 (R Knee)│
 *  │  FSR x8 (via CD74HC4067)    → GPIO32 (SIG), S0=25,S1=26,S2=27│
 *  │  Buzzer                     → GPIO13                          │
 *  │  LEDs x3                    → GPIO2, GPIO4, GPIO15            │
 *  │  RGB LED                    → R=16, G=17, B=5                 │
 *  │  Push Buttons x3            → GPIO33, GPIO36, GPIO39          │
 *  │  MicroSD (SPI)              → MOSI=23, MISO=19, SCK=18, CS=14│
 *  └─────────────────────────────────────────────────────────────────┘
 */

#include <Wire.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <SD.h>
#include <SPI.h>

// ========================== CONFIGURATION ==========================

// WiFi Credentials
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// WebSocket Server
const char* WS_HOST = "10.101.53.71";  // Your backend server IP
const uint16_t WS_PORT = 8000;
const char* WS_PATH = "/ws/sensor-data";

// Sampling
const unsigned long SAMPLE_INTERVAL_MS = 20;  // 50 Hz
const unsigned long OLED_UPDATE_MS     = 500;
const unsigned long SD_LOG_INTERVAL_MS = 100;  // 10 Hz for SD logging

// ========================== PIN DEFINITIONS ==========================

// I2C
#define I2C_SDA 21
#define I2C_SCL 22

// TCA9548A Multiplexer
#define TCA_ADDR 0x70

// Flex Sensors (Analog)
#define FLEX_LEFT_KNEE  34
#define FLEX_RIGHT_KNEE 35

// CD74HC4067 Analog MUX for FSRs
#define MUX_SIG 32
#define MUX_S0  25
#define MUX_S1  26
#define MUX_S2  27

// Buzzer
#define BUZZER_PIN 13

// LEDs
#define LED_1 2
#define LED_2 4
#define LED_3 15

// RGB LED
#define RGB_R 16
#define RGB_G 17
#define RGB_B 5

// Push Buttons (Active LOW)
#define BTN_1 33  // Toggle streaming
#define BTN_2 36  // Toggle display mode
#define BTN_3 39  // Manual alert

// MicroSD
#define SD_CS 14

// OLED
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_ADDR     0x3C

// ========================== GLOBAL OBJECTS ==========================

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
Adafruit_MPU6050 mpu[4];
WebSocketsClient webSocket;

// ========================== STATE VARIABLES ==========================

bool mpuReady[4]      = {false, false, false, false};
bool oledReady        = false;
bool sdReady          = false;
bool wsConnected      = false;
bool streamingEnabled = true;

// IMU data
struct IMUData {
  float ax, ay, az;
  float gx, gy, gz;
};
IMUData imuData[4];

// Sensor names for logging
const char* imuNames[] = {"left_thigh", "right_thigh", "left_shin", "right_shin"};
const char* fsrNames[] = {"l_heel", "l_toe", "l_outer", "l_inner", "r_heel", "r_toe", "r_outer", "r_inner"};

// Flex & FSR
float flexLeftKnee  = 0.0;
float flexRightKnee = 0.0;
uint16_t fsrValues[8] = {0};

// Buttons
bool btnState[3]     = {false, false, false};
bool lastBtnState[3] = {true, true, true};  // Pull-up = HIGH idle
unsigned long lastBtnDebounce[3] = {0, 0, 0};
const unsigned long DEBOUNCE_MS = 50;

// Timers
unsigned long lastSampleTime = 0;
unsigned long lastOLEDTime   = 0;
unsigned long lastSDLogTime  = 0;
unsigned long stepCount      = 0;

// Display mode
int displayMode = 0;  // 0=Status, 1=IMU, 2=Pressure

// SD card logging
File logFile;
String logFileName;

// ========================== TCA9548A MULTIPLEXER ==========================

void tcaSelect(uint8_t channel) {
  if (channel > 7) return;
  Wire.beginTransmission(TCA_ADDR);
  Wire.write(1 << channel);
  Wire.endTransmission();
}

// ========================== MUX READ (CD74HC4067) ==========================

uint16_t readMuxChannel(uint8_t channel) {
  // Set select pins (only using S0-S2 for 8 channels)
  digitalWrite(MUX_S0, (channel & 0x01) ? HIGH : LOW);
  digitalWrite(MUX_S1, (channel & 0x02) ? HIGH : LOW);
  digitalWrite(MUX_S2, (channel & 0x04) ? HIGH : LOW);
  delayMicroseconds(10);  // Allow MUX to settle
  return analogRead(MUX_SIG);
}

// ========================== SENSOR INITIALIZATION ==========================

void initIMUs() {
  Serial.println("[IMU] Initializing 4x MPU6050 via TCA9548A...");
  for (int i = 0; i < 4; i++) {
    tcaSelect(i);
    delay(10);
    if (mpu[i].begin(0x68, &Wire)) {
      mpu[i].setAccelerometerRange(MPU6050_RANGE_8_G);
      mpu[i].setGyroRange(MPU6050_RANGE_500_DEG);
      mpu[i].setFilterBandwidth(MPU6050_BAND_21_HZ);
      mpuReady[i] = true;
      Serial.printf("[IMU] MPU6050 #%d (%s) — OK\n", i, imuNames[i]);
    } else {
      mpuReady[i] = false;
      Serial.printf("[IMU] MPU6050 #%d (%s) — FAILED\n", i, imuNames[i]);
    }
  }
}

void initOLED() {
  Serial.println("[OLED] Initializing SSD1306...");
  // Select a free TCA channel or use direct I2C if OLED is not behind MUX
  // Assuming OLED is directly on the I2C bus (not through TCA)
  // Disable all TCA channels first to avoid conflicts
  Wire.beginTransmission(TCA_ADDR);
  Wire.write(0);
  Wire.endTransmission();
  delay(10);

  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    oledReady = true;
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println("OA Monitor v1.0");
    display.println("Initializing...");
    display.display();
    Serial.println("[OLED] OK");
  } else {
    Serial.println("[OLED] FAILED — continuing without display");
  }
}

void initSD() {
  Serial.println("[SD] Initializing MicroSD...");
  if (SD.begin(SD_CS)) {
    sdReady = true;
    // Create a new log file with timestamp
    logFileName = "/log_" + String(millis()) + ".csv";
    logFile = SD.open(logFileName, FILE_WRITE);
    if (logFile) {
      // Write CSV header
      logFile.println("timestamp,lt_ax,lt_ay,lt_az,lt_gx,lt_gy,lt_gz,"
                      "rt_ax,rt_ay,rt_az,rt_gx,rt_gy,rt_gz,"
                      "ls_ax,ls_ay,ls_az,ls_gx,ls_gy,ls_gz,"
                      "rs_ax,rs_ay,rs_az,rs_gx,rs_gy,rs_gz,"
                      "flex_l,flex_r,"
                      "fsr_lh,fsr_lt,fsr_lo,fsr_li,fsr_rh,fsr_rt,fsr_ro,fsr_ri");
      logFile.flush();
      Serial.printf("[SD] Logging to %s\n", logFileName.c_str());
    }
  } else {
    Serial.println("[SD] FAILED — continuing without logging");
  }
}

// ========================== PERIPHERAL INIT ==========================

void initPeripherals() {
  // Buzzer
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // LEDs
  pinMode(LED_1, OUTPUT);
  pinMode(LED_2, OUTPUT);
  pinMode(LED_3, OUTPUT);

  // RGB LED
  pinMode(RGB_R, OUTPUT);
  pinMode(RGB_G, OUTPUT);
  pinMode(RGB_B, OUTPUT);
  setRGB(255, 0, 0);  // Red = disconnected

  // Buttons (active low — ESP32 GPIO36/39 don't have internal pull-ups, use external)
  pinMode(BTN_1, INPUT_PULLUP);
  pinMode(BTN_2, INPUT);  // GPIO36 — no internal pull-up
  pinMode(BTN_3, INPUT);  // GPIO39 — no internal pull-up

  // MUX select pins
  pinMode(MUX_S0, OUTPUT);
  pinMode(MUX_S1, OUTPUT);
  pinMode(MUX_S2, OUTPUT);

  // Flex sensor pins
  pinMode(FLEX_LEFT_KNEE, INPUT);
  pinMode(FLEX_RIGHT_KNEE, INPUT);

  // Startup beep
  tone(BUZZER_PIN, 1000, 200);
  delay(250);
  tone(BUZZER_PIN, 1500, 200);
}

void setRGB(uint8_t r, uint8_t g, uint8_t b) {
  analogWrite(RGB_R, r);
  analogWrite(RGB_G, g);
  analogWrite(RGB_B, b);
}

// ========================== WiFi ==========================

void initWiFi() {
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    setRGB(0, 50, 0);  // Dim green
  } else {
    Serial.println("\n[WiFi] FAILED — will retry in background");
  }
}

// ========================== WEBSOCKET ==========================

void webSocketEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      wsConnected = false;
      setRGB(255, 0, 0);  // Red
      Serial.println("[WS] Disconnected");
      break;

    case WStype_CONNECTED:
      wsConnected = true;
      setRGB(0, 255, 0);  // Green
      Serial.println("[WS] Connected to server");
      break;

    case WStype_TEXT: {
      // Parse incoming commands from server
      StaticJsonDocument<256> doc;
      DeserializationError err = deserializeJson(doc, payload, length);
      if (!err) {
        // Handle alert command
        if (doc.containsKey("alert") && doc["alert"].as<bool>()) {
          tone(BUZZER_PIN, 2000, 500);
          digitalWrite(LED_1, HIGH);
          delay(100);
          digitalWrite(LED_1, LOW);
        }
        // Handle buzzer
        if (doc.containsKey("buzzer")) {
          int beeps = doc["buzzer"].as<int>();
          for (int i = 0; i < beeps; i++) {
            tone(BUZZER_PIN, 1500, 150);
            delay(200);
          }
        }
        // Handle LED control
        if (doc.containsKey("led")) {
          JsonArray leds = doc["led"].as<JsonArray>();
          if (leds.size() >= 3) {
            digitalWrite(LED_1, leds[0].as<int>() ? HIGH : LOW);
            digitalWrite(LED_2, leds[1].as<int>() ? HIGH : LOW);
            digitalWrite(LED_3, leds[2].as<int>() ? HIGH : LOW);
          }
        }
      }
      break;
    }

    case WStype_PING:
    case WStype_PONG:
      break;
  }
}

void initWebSocket() {
  webSocket.begin(WS_HOST, WS_PORT, WS_PATH);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);
  Serial.println("[WS] WebSocket client initialized");
}

// ========================== SENSOR READING ==========================

void readAllSensors() {
  // 1. Read IMUs
  for (int i = 0; i < 4; i++) {
    if (!mpuReady[i]) continue;
    tcaSelect(i);
    sensors_event_t accel, gyro, temp;
    mpu[i].getEvent(&accel, &gyro, &temp);
    imuData[i].ax = accel.acceleration.x;
    imuData[i].ay = accel.acceleration.y;
    imuData[i].az = accel.acceleration.z;
    imuData[i].gx = gyro.gyro.x;
    imuData[i].gy = gyro.gyro.y;
    imuData[i].gz = gyro.gyro.z;
  }

  // 2. Read Flex Sensors
  int rawFlexL = analogRead(FLEX_LEFT_KNEE);
  int rawFlexR = analogRead(FLEX_RIGHT_KNEE);
  // Map ADC (0-4095) to approximate degrees (0-180)
  flexLeftKnee  = map(rawFlexL, 0, 4095, 0, 180);
  flexRightKnee = map(rawFlexR, 0, 4095, 0, 180);

  // 3. Read 8 FSRs via analog MUX
  for (int ch = 0; ch < 8; ch++) {
    fsrValues[ch] = readMuxChannel(ch);
  }
}

// ========================== DATA STREAMING ==========================

void sendSensorData() {
  if (!wsConnected || !streamingEnabled) return;

  StaticJsonDocument<1024> doc;
  doc["ts"] = millis();

  // IMU data
  JsonObject imu = doc.createNestedObject("imu");
  for (int i = 0; i < 4; i++) {
    JsonObject sensor = imu.createNestedObject(imuNames[i]);
    sensor["ax"] = round(imuData[i].ax * 100) / 100.0;
    sensor["ay"] = round(imuData[i].ay * 100) / 100.0;
    sensor["az"] = round(imuData[i].az * 100) / 100.0;
    sensor["gx"] = round(imuData[i].gx * 100) / 100.0;
    sensor["gy"] = round(imuData[i].gy * 100) / 100.0;
    sensor["gz"] = round(imuData[i].gz * 100) / 100.0;
  }

  // Flex sensors
  JsonObject flex = doc.createNestedObject("flex");
  flex["left_knee"]  = flexLeftKnee;
  flex["right_knee"] = flexRightKnee;

  // FSR pressure sensors
  JsonObject fsr = doc.createNestedObject("fsr");
  JsonObject leftFoot  = fsr.createNestedObject("left_foot");
  leftFoot["heel"]  = fsrValues[0];
  leftFoot["toe"]   = fsrValues[1];
  leftFoot["outer"] = fsrValues[2];
  leftFoot["inner"] = fsrValues[3];
  JsonObject rightFoot = fsr.createNestedObject("right_foot");
  rightFoot["heel"]  = fsrValues[4];
  rightFoot["toe"]   = fsrValues[5];
  rightFoot["outer"] = fsrValues[6];
  rightFoot["inner"] = fsrValues[7];

  // Button states
  JsonObject buttons = doc.createNestedObject("buttons");
  buttons["btn1"] = btnState[0];
  buttons["btn2"] = btnState[1];
  buttons["btn3"] = btnState[2];

  // Serialize and send
  char buffer[1024];
  size_t len = serializeJson(doc, buffer);
  webSocket.sendTXT(buffer, len);

  // Blink blue while streaming
  setRGB(0, 0, 100);
  delayMicroseconds(500);
  setRGB(0, 255, 0);
}

// ========================== SD LOGGING ==========================

void logToSD() {
  if (!sdReady || !logFile) return;

  // CSV row: timestamp, 4x IMU (6 vals each = 24), 2x flex, 8x FSR
  logFile.print(millis());
  for (int i = 0; i < 4; i++) {
    logFile.printf(",%.2f,%.2f,%.2f,%.2f,%.2f,%.2f",
      imuData[i].ax, imuData[i].ay, imuData[i].az,
      imuData[i].gx, imuData[i].gy, imuData[i].gz);
  }
  logFile.printf(",%.1f,%.1f", flexLeftKnee, flexRightKnee);
  for (int i = 0; i < 8; i++) {
    logFile.printf(",%d", fsrValues[i]);
  }
  logFile.println();

  // Flush every 10 writes
  static int flushCounter = 0;
  if (++flushCounter >= 10) {
    logFile.flush();
    flushCounter = 0;
  }
}

// ========================== BUTTON HANDLING ==========================

void readButtons() {
  uint8_t pins[] = {BTN_1, BTN_2, BTN_3};
  for (int i = 0; i < 3; i++) {
    bool reading = digitalRead(pins[i]) == LOW;  // Active LOW
    if (reading != lastBtnState[i]) {
      lastBtnDebounce[i] = millis();
    }
    if ((millis() - lastBtnDebounce[i]) > DEBOUNCE_MS) {
      if (reading && !btnState[i]) {
        // Button just pressed
        switch (i) {
          case 0:  // Toggle streaming
            streamingEnabled = !streamingEnabled;
            Serial.printf("[BTN] Streaming %s\n", streamingEnabled ? "ON" : "OFF");
            tone(BUZZER_PIN, streamingEnabled ? 1500 : 800, 100);
            break;
          case 1:  // Toggle display mode
            displayMode = (displayMode + 1) % 3;
            Serial.printf("[BTN] Display mode: %d\n", displayMode);
            break;
          case 2:  // Manual alert
            Serial.println("[BTN] Manual alert triggered");
            tone(BUZZER_PIN, 2500, 300);
            break;
        }
      }
      btnState[i] = reading;
    }
    lastBtnState[i] = reading;
  }
}

// ========================== OLED DISPLAY ==========================

void updateOLED() {
  if (!oledReady) return;

  // Briefly disable TCA to talk to OLED on main I2C bus
  Wire.beginTransmission(TCA_ADDR);
  Wire.write(0);
  Wire.endTransmission();

  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);

  switch (displayMode) {
    case 0:  // Status overview
      display.println("=== OA MONITOR ===");
      display.println();
      display.printf("WiFi: %s\n", WiFi.status() == WL_CONNECTED ? "OK" : "N/A");
      display.printf("WS:   %s\n", wsConnected ? "Connected" : "Offline");
      display.printf("Stream: %s\n", streamingEnabled ? "ON" : "OFF");
      display.printf("Steps: %lu\n", stepCount);
      display.printf("SD: %s\n", sdReady ? "Logging" : "N/A");
      break;

    case 1:  // IMU data
      display.println("== IMU DATA ==");
      for (int i = 0; i < 4; i++) {
        if (mpuReady[i]) {
          display.printf("%s: %.1f\n", imuNames[i], 
            sqrt(imuData[i].ax*imuData[i].ax + imuData[i].ay*imuData[i].ay + imuData[i].az*imuData[i].az));
        }
      }
      display.printf("\nFlex L:%.0f R:%.0f", flexLeftKnee, flexRightKnee);
      break;

    case 2:  // Pressure data
      display.println("== PRESSURE ==");
      display.println("LEFT FOOT:");
      display.printf(" H:%4d T:%4d\n", fsrValues[0], fsrValues[1]);
      display.printf(" O:%4d I:%4d\n", fsrValues[2], fsrValues[3]);
      display.println("RIGHT FOOT:");
      display.printf(" H:%4d T:%4d\n", fsrValues[4], fsrValues[5]);
      display.printf(" O:%4d I:%4d\n", fsrValues[6], fsrValues[7]);
      break;
  }

  display.display();
}

// ========================== SETUP ==========================

void setup() {
  Serial.begin(115200);
  Serial.println("\n========================================");
  Serial.println("  OA MONITORING WEARABLE - Starting...");
  Serial.println("========================================\n");

  // Initialize I2C
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000);  // 400kHz fast I2C

  // Initialize peripherals
  initPeripherals();

  // Initialize sensors
  initOLED();
  initIMUs();
  initSD();

  // Connect WiFi & WebSocket
  initWiFi();
  initWebSocket();

  // Ready indicator
  digitalWrite(LED_1, HIGH);
  delay(200);
  digitalWrite(LED_1, LOW);
  digitalWrite(LED_2, HIGH);
  delay(200);
  digitalWrite(LED_2, LOW);
  digitalWrite(LED_3, HIGH);
  delay(200);
  digitalWrite(LED_3, LOW);

  Serial.println("\n[SYSTEM] Initialization complete. Starting main loop.\n");
}

// ========================== MAIN LOOP ==========================

void loop() {
  unsigned long now = millis();

  // WebSocket maintenance (non-blocking)
  webSocket.loop();

  // Read buttons (always responsive)
  readButtons();

  // Main sensor read + stream at 50Hz
  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = now;
    readAllSensors();
    sendSensorData();
  }

  // SD logging at 10Hz
  if (now - lastSDLogTime >= SD_LOG_INTERVAL_MS) {
    lastSDLogTime = now;
    logToSD();
  }

  // OLED update at 2Hz
  if (now - lastOLEDTime >= OLED_UPDATE_MS) {
    lastOLEDTime = now;
    updateOLED();
  }
}
