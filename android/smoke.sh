#!/bin/sh
set -eux
adb install --no-incremental -g android/para-unsigned.apk
adb install --no-incremental -t android/test.apk
adb shell wm size 780x1680
adb shell wm density 320
adb reverse tcp:18787 tcp:18787
adb shell am start -W -n ru.para.wake/.Main
fixture=$(mktemp -d)
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' -keyout "$fixture/key" -out "$fixture/cert" 2>/dev/null
python3 android/test/plan_server.py "$fixture/cert" "$fixture/key" &
server=$!
trap 'kill "$server" 2>/dev/null || true; rm -rf "$fixture"' EXIT
for i in $(seq 1 25); do
    if curl --silent --output /dev/null --cacert "$fixture/cert" https://127.0.0.1:18787/device/nativeplan; then break; fi
    sleep 1
done
ca=$(openssl x509 -in "$fixture/cert" -outform DER | base64 -w0)
if ! result=$(timeout 150 adb shell am instrument -e ca "$ca" -w ru.para.wake.test/ru.para.wake.AlarmCheck); then
    adb logcat -d -b crash
    exit 1
fi
echo "$result"
echo "$result" | grep -F 'alarm lifecycle passed'
adb pull /sdcard/Android/data/ru.para.wake/files/clock-preview.png "$RUNNER_TEMP/clock-preview.png"
