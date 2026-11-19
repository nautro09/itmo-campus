package ru.para.wake;

import android.content.*;
import android.util.Base64;
import java.io.*;
import java.net.URL;
import java.security.KeyStore;
import java.security.cert.CertificateFactory;
import java.time.*;
import javax.net.ssl.*;
import org.json.JSONObject;

final class PlanScenario {
    static final String SITE="https://127.0.0.1:18787";
    static final String CODE="abcdefghijklmnopqrstuvwx";
    static void check(boolean ok,String detail){if(!ok)throw new AssertionError(detail);}
    static void connect(Context c,String cert) throws Exception {
        KeyStore ca=KeyStore.getInstance(KeyStore.getDefaultType());ca.load(null);
        ca.setCertificateEntry("fixture",CertificateFactory.getInstance("X.509")
            .generateCertificate(new ByteArrayInputStream(Base64.decode(cert,Base64.DEFAULT))));
        TrustManagerFactory trust=TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());trust.init(ca);
        SSLContext tls=SSLContext.getInstance("TLS");tls.init(null,trust.getTrustManagers(),null);
        HttpsURLConnection.setDefaultSSLSocketFactory(tls.getSocketFactory()); // instrumentation process only
        Link.pair(c,SITE,CODE);
        Link.sync(c);
        JSONObject row=NativeClock.current(c);
        check("08:30".equals(NativeClock.time(row)) && "09:50".equals(row.getString("start"))
            && "rule".equals(row.getString("basis")),"server: 09:50 must mean 08:30 for a mixed-format class");
    }
    static void step(String name)throws Exception{
        HttpsURLConnection conn=(HttpsURLConnection)new URL(SITE+"/test/"+name).openConnection();
        try{conn.setConnectTimeout(5000);conn.setReadTimeout(5000);conn.setRequestMethod("POST");
            check(conn.getResponseCode()==200,"fixture: "+name);
        }finally{conn.disconnect();}
    }
    static void changes(Context c)throws Exception{
        SharedPreferences p=Link.prefs(c);
        String rev=p.getString("revision","");
        Link.request(c,"applied",rev);step("verified");
        p.edit().putBoolean("autoClock",true).commit();
        step("relink");Link.pair(c,SITE,CODE);
        check(p.getBoolean("autoClock",false),"same bot, keep permission after QR repair");
        step("reschedule");Link.sync(c);
        JSONObject newPlan=NativeClock.current(c);
        check(NativeClock.time(newPlan).equals("07:45") && !rev.equals(p.getString("revision","")),"changed rule");
        p.edit().putString("site","https://127.0.0.1:18789").commit();
        try{Link.sync(c);throw new AssertionError("offline");}catch(IOException expected){}
        check(!p.getString("syncIssue","").isEmpty() && NativeClock.usable(p,newPlan,Instant.now()),"offline set plan");
        check(!NativeClock.usable(p,newPlan,Instant.now().plusSeconds(13*3600)),"expired cached plan");
        p.edit().putString("site",SITE).commit();Link.sync(c);
        check(p.getString("syncIssue","").isEmpty(),"connectivity recovered");
        step("revoke");
        try{Link.sync(c);throw new AssertionError("revoked");}catch(Link.HttpFailure e){check(e.status==401,"401");}
        check(!NativeClock.usable(p,newPlan,Instant.now()),"refusal blocks cached plan");
        ZoneId zone=NativeClock.MOSCOW;
        Instant wake=Instant.parse("2026-11-20T05:30:00Z");
        check(NativeClock.nextRingMatches(Instant.parse("2026-11-19T12:00:00Z"),wake,zone),"can install at 15:00");
        check(!NativeClock.nextRingMatches(Instant.parse("2026-11-19T04:00:00Z"),wake,zone),"would ring today");
    }
}
