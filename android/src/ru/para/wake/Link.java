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
            if(h.getResponseCode()!=200) throw new IOException("Сервер не подтвердил запрос ("+h.getResponseCode()+").");
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            try(InputStream in=h.getInputStream()){
                byte[] buf=new byte[1024]; int n;
                while((n=in.read(buf))!=-1){if(out.size()+n>4096) throw new IOException("Ответ слишком большой.");out.write(buf,0,n);}
            }
            String body=out.toString("UTF-8");
            if(!pair && !MessageDigest.isEqual(bytes(mac(credential,nonce+"\n"+body)),bytes(String.valueOf(h.getHeaderField("X-Wake-MAC")))))
                throw new IOException("Подпись сервера не подтверждена.");
            return new JSONObject(body);
        } finally {h.disconnect();}
    }
    static void pair(Context c,String site,String code) throws Exception {
        site=origin(site);
        if(!code.matches("[A-Za-z0-9_-]{24}")) throw new IOException("Проверь одноразовый код.");
        String secret=call(site,"pair",code,"").getString("token");
        if(!secret.matches("[A-Za-z0-9_-]{43}")) throw new IOException("Ответ привязки недействителен.");
        String deviceKey=hex(MessageDigest.getInstance("SHA-256").digest(bytes(secret)));
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE,key());
        if(!prefs(c).edit().clear().putString("site",site).putString("iv",Base64.encodeToString(cipher.getIV(),2))
            .putString("cipher",Base64.encodeToString(cipher.doFinal(bytes(deviceKey)),2)).commit()) throw new IOException("Не удалось сохранить привязку.");
        SyncJob.enable(c);
    }
    static JSONObject request(Context c,String op,String revision) throws Exception {
        SharedPreferences p=prefs(c);
        if(!p.contains("cipher")) throw new IOException("Сначала привяжи телефон.");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(p.getString("iv",""),2)));
        String credential=new String(cipher.doFinal(Base64.decode(p.getString("cipher",""),2)),StandardCharsets.UTF_8);
        String site=origin(p.getString("site",""));
        return call(site,op,credential,revision);
    }
    static void sync(Context c) throws Exception {
        JSONObject plan=request(c,"nativeplan","");
        NativeClock.receive(c,plan);
        request(c,"received",plan.getString("revision"));
    }
}
