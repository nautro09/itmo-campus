package ru.para.wake;

import android.content.*;
import android.security.keystore.*;
import android.util.Base64;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.UUID;
import javax.crypto.*;
import javax.crypto.spec.*;
import javax.net.ssl.HttpsURLConnection;

final class Link {
    static final String ALIAS = "para.wake.device";
    static final java.util.concurrent.ExecutorService worker = java.util.concurrent.Executors.newSingleThreadExecutor();
    static android.content.SharedPreferences prefs(Context c) { return c.getSharedPreferences("link",0); }
    static byte[] bytes(String s) { return s.getBytes(StandardCharsets.UTF_8); }
    static String hex(byte[] data) {
        StringBuilder b=new StringBuilder();
        for(byte x:data) b.append(Character.forDigit((x>>4)&15,16)).append(Character.forDigit(x&15,16));
        return b.toString();
    }
    static String mac(String key,String data) throws Exception {
        Mac m=Mac.getInstance("HmacSHA256");
        m.init(new SecretKeySpec(bytes(key),"HmacSHA256"));
        return hex(m.doFinal(bytes(data)));
    }
    static String origin(String input) throws Exception {
        URI u=new URI(input.trim());
        if(!"https".equals(u.getScheme()) || u.getHost()==null || u.getUserInfo()!=null ||
            u.getQuery()!=null || u.getFragment()!=null || !(u.getPath().isEmpty() || "/".equals(u.getPath())))
            throw new IOException("Нужен HTTPS-адрес без пути.");
        return "https://"+u.getRawAuthority();
    }
    static SecretKey key() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if(store.containsAlias(ALIAS)) return (SecretKey)store.getKey(ALIAS,null);
        KeyGenerator g=KeyGenerator.getInstance("AES","AndroidKeyStore");
        g.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes("GCM").setEncryptionPaddings("NoPadding").build());
        return g.generateKey();
    }
    static JSONObject call(String site,String op,String credential,String revision) throws Exception {
        String nonce=UUID.randomUUID().toString().replace("-","");
        String stamp=Long.toString(System.currentTimeMillis()/1000);
        boolean pair=op.equals("pair");
        HttpsURLConnection h=(HttpsURLConnection)new URL(site+"/device/"+op).openConnection();
        try {
            h.setInstanceFollowRedirects(false);
            h.setConnectTimeout(8000); h.setReadTimeout(8000); h.setUseCaches(false);
            h.setRequestMethod("POST");
            h.setRequestProperty("Authorization","Bearer "+(pair?credential:mac(credential,op+"\n"+stamp+"\n"+nonce+"\n"+revision)));
            h.setRequestProperty("X-Wake-Time",stamp); h.setRequestProperty("X-Wake-Nonce",nonce);
            if(!revision.isEmpty()) h.setRequestProperty("X-Wake-Revision",revision);
            int status=h.getResponseCode();
            if(status!=200) throw new HttpFailure(status);
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            try(InputStream in=h.getInputStream()){
                byte[] buf=new byte[1024]; int n;
                while((n=in.read(buf))!=-1){if(out.size()+n>4096) throw new IOException("Ответ слишком большой.");out.write(buf,0,n);}
            }
            String body=out.toString("UTF-8");
            if(!pair && !MessageDigest.isEqual(bytes(mac(credential,nonce+"\n"+body)),bytes(String.valueOf(h.getHeaderField("X-Wake-MAC")))))
                throw new SignatureException("response MAC");
            return new JSONObject(body);
        } finally {h.disconnect();}
    }
    static void pair(Context c,String site,String code) throws Exception {
        site=origin(site);
        if(!code.matches("[A-Za-z0-9_-]{24}")) throw new IOException("Проверь одноразовый код.");
        JSONObject response=call(site,"pair",code,"");
        String secret=response.getString("token");
        if(!secret.matches("[A-Za-z0-9_-]{43}")) throw new IOException("Ответ привязки недействителен.");
        boolean keepAuto=false;
        SharedPreferences p=prefs(c);
        if(p.getBoolean("autoClock",false) && response.has("continuity")){
            try{
                String proof=mac(deviceCredential(p),"relink\n"+site+"\n"+secret);
                keepAuto=MessageDigest.isEqual(bytes(proof),bytes(response.getString("continuity")));
            }catch(Exception unavailable){ /* A valid QR can also replace an unreadable old key. */ }
        }
        String deviceKey=hex(MessageDigest.getInstance("SHA-256").digest(bytes(secret)));
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE,key());
        if(!p.edit().clear().putBoolean("autoClock",keepAuto).putString("site",site).putString("iv",Base64.encodeToString(cipher.getIV(),2))
            .putString("cipher",Base64.encodeToString(cipher.doFinal(bytes(deviceKey)),2)).commit()) throw new IOException("Не удалось сохранить привязку.");
        SyncJob.enable(c);
        if(!keepAuto && ClockAccess.ready())ClockAccess.stopLocal();
    }
    private static String deviceCredential(SharedPreferences p) throws Exception {
        if(!p.contains("cipher")) throw new IOException("Сначала привяжи телефон.");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(p.getString("iv",""),2)));
        return new String(cipher.doFinal(Base64.decode(p.getString("cipher",""),2)),StandardCharsets.UTF_8);
    }
    static JSONObject request(Context c,String op,String revision) throws Exception {
        SharedPreferences p=prefs(c);
        String credential=deviceCredential(p);
        String site=origin(p.getString("site",""));
        return call(site,op,credential,revision);
    }
    static final class HttpFailure extends IOException {
        final int status;
        HttpFailure(int status){super("HTTP "+status);this.status=status;}
    }

    static String explain(Context c, Exception e) {
        int code = e instanceof HttpFailure ? ((HttpFailure)e).status : 0;
        if (code == 401 || code == 403)
            return "Сервер отклонил привязку. Проверь автоматическое время Android и открой новый QR из своего бота.";
        if (e instanceof GeneralSecurityException || e instanceof javax.net.ssl.SSLException)
            return "Не удалось проверить ключ или защищённое соединение. Проверь дату телефона и привязку.";
        if (code == 409) return "Расписание изменилось во время проверки. Запрашиваю новый план.";
        android.net.ConnectivityManager cm = c.getSystemService(android.net.ConnectivityManager.class);
        if (cm.getActiveNetwork() == null) return "Телефон без сети. Проверка повторится при подключении.";
        String site=prefs(c).getString("site","");
        if (site.endsWith(".trycloudflare.com") && (e instanceof UnknownHostException || code==404 || code==410 || code==502 || code==503 || code==530))
            return "Временный адрес сервера недоступен. После перезапуска туннеля открой свежий QR из Telegram.";
        if (e instanceof SocketTimeoutException) return "Сервер долго не отвечает. Повторю запрос автоматически.";
        if (code != 0) return "Сервер ответил HTTP "+code+". Проверь доступность адреса в Telegram.";
        if (e instanceof JSONException) return "Сервер прислал несовместимый план. Проверь версию бота.";
        return "Нет соединения с сервером. Проверь сеть телефона и работает ли бот.";
    }

    static void syncIfDue(Context c) throws Exception {
        SharedPreferences p=prefs(c);
        long age=System.currentTimeMillis()-p.getLong("lastAttempt",0);
        if(!p.contains("cipher"))return;
        if(age<0 || age>=NativeClock.MINUTE){sync(c);return;}
        ClockAccess.refresh();
    }

    static void sync(Context c) throws Exception {
        SharedPreferences p=prefs(c);
        p.edit().putLong("lastAttempt",System.currentTimeMillis()).apply();
        try {
            for(int attempt=0;attempt<2;attempt++){
                JSONObject plan=request(c,"nativeplan","");
                NativeClock.receive(c,plan);
                String rev=plan.getString("revision");
                try {
                    request(c,"received",rev);
                    if(rev.equals(p.getString("autoApplied","")) && !rev.equals(p.getString("autoReported",""))){
                        request(c,"applied",rev);
                        p.edit().putString("autoReported",rev).apply();
                    }
                } catch(HttpFailure e) {
                    if(e.status==409 && attempt==0){p.edit().putBoolean("syncBlocked",true).apply();continue;}
                    if(e.status<500)throw e;
                    p.edit().putString("ackIssue","Статус будет отправлен при следующей связи").apply();
                } catch(IOException e) {
                    if(e instanceof javax.net.ssl.SSLException)throw e;
                    p.edit().putString("ackIssue","Статус будет отправлен при следующей связи").apply();
                }
                return;
            }
        } catch(Exception e) {
            boolean blocked=e instanceof GeneralSecurityException || e instanceof javax.net.ssl.SSLException
                || e instanceof JSONException || e instanceof HttpFailure && ((HttpFailure)e).status<500
                    && ((HttpFailure)e).status!=404 && ((HttpFailure)e).status!=410;
            // A transient network failure cannot clear an earlier refusal from the server.
            p.edit().putString("syncIssue",explain(c,e)).putBoolean("syncBlocked",blocked || p.getBoolean("syncBlocked",false)).apply();
            throw e;
        } finally {
            ClockAccess.refresh();
        }
    }
}
