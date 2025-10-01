#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

#define ENDPOINT "http://doortron.roboclub.org/update"
#define URL0 (ENDPOINT "/" THE_KEY "/0")
#define URL1 (ENDPOINT "/" THE_KEY "/1")

void setup() {

  Serial.begin(115200);
  Serial.println();
  Serial.println(WiFi.macAddress());
  Serial.print("Connecting");

  WiFi.mode(WIFI_STA);
  WiFi.begin("CMU-DEVICE");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());

  pinMode(D5, INPUT_PULLUP);

}

void loop() {
  // wait for WiFi connection
  if ((WiFi.status() == WL_CONNECTED)) {

    WiFiClient client;

    HTTPClient http;

    Serial.print("[HTTP] begin...\n");

    int q = digitalRead(D5);
    Serial.println(q);
    const char *url = q ? URL1 : URL0;

    if (http.begin(client, url)) {


      Serial.print("[HTTP] GET...\n");
      // start connection and send HTTP header
      int httpCode = http.GET();

      // httpCode will be negative on error
      if (httpCode > 0) {
        // HTTP header has been send and Server response header has been handled
        Serial.printf("[HTTP] GET... code: %d\n", httpCode);

        // file found at server
        if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_MOVED_PERMANENTLY) {
          String payload = http.getString();
          Serial.println(payload);
        }
      } else {
        Serial.printf("[HTTP] GET... failed, error: %s\n", http.errorToString(httpCode).c_str());
      }

      http.end();
    } else {
      Serial.printf("[HTTP} Unable to connect\n");
    }
  }

  delay(5000);
}
