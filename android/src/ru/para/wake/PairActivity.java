package ru.para.wake;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import java.io.IOException;

public final class PairActivity extends Activity {
    static String[] ticket(Intent intent) throws Exception {
        Uri uri = intent.getData();
        if (!Intent.ACTION_VIEW.equals(intent.getAction()) || uri == null || !uri.isHierarchical()
                || !"para-clock".equals(uri.getScheme()) || !"pair".equals(uri.getEncodedAuthority())
                || !uri.getPath().isEmpty() || uri.getFragment() != null
                || uri.getQueryParameterNames().size() != 2
                || uri.getQueryParameters("site").size() != 1 || uri.getQueryParameters("code").size() != 1)
            throw new IOException("Ссылка привязки недействительна.");
        String site = Link.origin(uri.getQueryParameter("site"));
        String code = uri.getQueryParameter("code");
        if (!code.matches("[A-Za-z0-9_-]{24}")) throw new IOException("Код недействителен.");
        return new String[]{site, code};
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        final String[] ticket;
        try { ticket = ticket(getIntent()); }
        catch (Exception invalid) { error("Открой новый QR из своего Telegram-бота."); return; }
        boolean linked = Link.prefs(this).contains("cipher");
        new AlertDialog.Builder(this).setTitle(linked ? "Заменить привязку телефона?" : "Привязать телефон?")
            .setMessage("Проверь адрес из своего бота:\n" + ticket[0])
            .setNegativeButton("Отмена", (d,w) -> finish()).setOnCancelListener(d -> finish())
            .setPositiveButton("Привязать", (d,w) -> connect(ticket[0], ticket[1])).show();
    }

    private void connect(String site, String code) {
        android.widget.TextView progress = new android.widget.TextView(this);
        progress.setText("Подключаю телефон…");
        progress.setGravity(android.view.Gravity.CENTER);
        setContentView(progress);
        Link.worker.execute(() -> {
            try {
                Link.pair(this, site, code);
                // Main refreshes the plan when it resumes, including after an existing pairing.
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    startActivity(new Intent(this, Main.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP));
                    finish();
                });
            } catch (Exception failed) {
                runOnUiThread(() -> {
                    if (!isFinishing() && !isDestroyed())
                        error(Link.explain(this,failed)+" Код привязки действует пять минут.");
                });
            }
        });
    }

    private void error(String message) {
        new AlertDialog.Builder(this).setMessage(message)
            .setPositiveButton("Закрыть", (d,w) -> finish()).setOnCancelListener(d -> finish()).show();
    }
}
