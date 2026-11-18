#!/bin/sh
set -eux
adb install --no-incremental -g android/para-unsigned.apk
adb install --no-incremental -t android/test.apk
adb shell appops set ru.para.wake SCHEDULE_EXACT_ALARM allow
adb shell am start -W -n ru.para.wake/.Main
result=$(adb shell am instrument -w ru.para.wake.test/ru.para.wake.AlarmCheck)
echo "$result"
echo "$result" | grep -F 'alarm lifecycle passed'
