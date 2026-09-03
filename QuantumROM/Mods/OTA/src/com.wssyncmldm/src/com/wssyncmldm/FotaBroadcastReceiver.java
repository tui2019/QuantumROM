package com.wssyncmldm;

import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;

public class FotaBroadcastReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        try {
            Intent launchIntent = new Intent();
            launchIntent.setComponent(new ComponentName("org.lineageos.updater", "org.lineageos.updater.UpdatesActivity"));
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(launchIntent);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
