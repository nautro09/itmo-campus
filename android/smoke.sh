#!/bin/sh
set -eux
adb install --no-incremental -g android/para-unsigned.apk
adb install --no-incremental -t android/test.apk
adb shell am start -W -n ru.para.wake/.Main
if ! result=$(timeout 150 adb shell am instrument -w ru.para.wake.test/ru.para.wake.AlarmCheck); then
    adb logcat -d -b crash
    exit 1
fi
echo "$result"
echo "$result" | grep -F 'alarm lifecycle passed'
