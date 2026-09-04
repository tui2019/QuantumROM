SKIPUNZIP=0

ui_print "****************************************"
ui_print "*   Project Revive SM-P613 Camera Fix  *"
ui_print "*   - libcore2nativeutil (QCOM vendor) *"
ui_print "*   - libstagefright (FORTIFY fix)     *"
ui_print "****************************************"

set_perm_recursive $MODPATH 0 0 0755 0644
set_perm_recursive $MODPATH/system/lib 0 0 0755 0644
set_perm_recursive $MODPATH/system/lib64 0 0 0755 0644

ui_print "- Files installed to /system overlay."
ui_print "- Restart your device or cameraserver."
