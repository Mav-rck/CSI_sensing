#include <WiFi.h>
#include <esp_wifi.h>

// Replace with your Wi-Fi credentials
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

// The callback function triggered every time a Wi-Fi packet is received
void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf) return;

    // FIX: Extract RSSI directly from rx_ctrl in newer ESP-IDF versions
    int8_t rssi = info->rx_ctrl.rssi;
    
    // Extract raw CSI payload (Complex numbers: Real & Imaginary)
    int8_t *csi_data = info->buf;
    uint16_t csi_len = info->len;
    
    // Print the data as a CSV stream to the PC
    // Format: CSI_START, RSSI, DataLength, [Real, Imag, Real, Imag...], CSI_END
    Serial.print("CSI_START,");
    Serial.print(rssi);
    Serial.print(",");
    Serial.print(csi_len);
    Serial.print(",");
    
    for (int i = 0; i < csi_len; i++) {
        Serial.print(csi_data[i]);
        Serial.print(",");
    }
    Serial.println("CSI_END");
}

void setup() {
    // 921600 baud rate is mandatory to prevent buffer overflow
    Serial.begin(921600);
    
    // Connect to Wi-Fi to establish a reliable Tx/Rx link with the router
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
    }
    
    // 1. Enable Promiscuous Mode so the ESP32 can inspect packet headers
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    
    // 2. Configure CSI parameters
    wifi_csi_config_t csi_config = {
        .lltf_en           = true,
        .htltf_en          = true,
        .stbc_htltf2_en    = true,
        .ltf_merge_en      = true,
        .channel_filter_en = true,
        .manu_scale        = false,
        .shift             = false,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    
    // 3. Register the callback function
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL));
    
    // 4. Enable CSI data collection
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

void loop() {
    // Ping the gateway router to generate multipath signals
    IPAddress gateway = WiFi.gatewayIP();
    WiFi.hostByName(gateway.toString().c_str(), gateway);
    
    delay(50); 
}