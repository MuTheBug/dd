package com.haqquna.app;

import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import java.io.IOException;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "Haqquna";
    private static final String PREFS = "haqquna_prefs";
    private static final String KEY_SERVER = "server_address";
    private static final int PROXY_PORT = 8765;

    private WebView webView;
    private LocalProxy proxy;
    private String serverAddress;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        serverAddress = prefs.getString(KEY_SERVER, getString(R.string.default_server));

        startProxy();
        setupUI();
        loadForm();
    }

    private void startProxy() {
        String base = serverAddress;
        if (!base.startsWith("http")) base = "http://" + base;
        proxy = new LocalProxy(this, PROXY_PORT, base);
        try {
            proxy.start();
            Log.i(TAG, "Local proxy started on port " + PROXY_PORT +
                    " → forwarding to " + base);
        } catch (IOException e) {
            Log.e(TAG, "Failed to start proxy", e);
            Toast.makeText(this, "فشل تشغيل الخادم المحلي", Toast.LENGTH_LONG).show();
        }
    }

    private void setupUI() {
        // Root layout
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        // Top bar with settings button
        FrameLayout topBar = new FrameLayout(this);
        topBar.setBackgroundColor(Color.parseColor("#1e3a8a"));
        int barHeight = (int) (40 * getResources().getDisplayMetrics().density);
        topBar.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, barHeight));

        ImageButton settingsBtn = new ImageButton(this);
        settingsBtn.setImageResource(android.R.drawable.ic_menu_manage);
        settingsBtn.setBackgroundColor(Color.TRANSPARENT);
        settingsBtn.setColorFilter(Color.WHITE);
        settingsBtn.setPadding(16, 8, 16, 8);
        settingsBtn.setContentDescription("إعدادات السرفر");
        FrameLayout.LayoutParams btnParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.MATCH_PARENT);
        btnParams.gravity = Gravity.START | Gravity.CENTER_VERTICAL;
        settingsBtn.setLayoutParams(btnParams);
        settingsBtn.setOnClickListener(v -> showServerSettings());
        topBar.addView(settingsBtn);

        TextView title = new TextView(this);
        title.setText("حقنا — " + serverAddress);
        title.setTextColor(Color.WHITE);
        title.setTextSize(13);
        title.setGravity(Gravity.CENTER);
        title.setLayoutParams(new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        title.setTag("titleText");
        topBar.addView(title);
        topBar.setTag("topBar");

        root.addView(topBar);

        // WebView
        webView = new WebView(this);
        webView.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUserAgentString(settings.getUserAgentString() + " HaqqunaApp/1.0");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                // Auto-set the server URL in the form to go through proxy
                view.evaluateJavascript(
                    "if(document.getElementById('serverUrl')){" +
                    "  document.getElementById('serverUrl').value='http://localhost:" + PROXY_PORT + "';" +
                    "  try{localStorage.setItem('haqquna_server','http://localhost:" + PROXY_PORT + "');}catch(e){}" +
                    "}", null);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                                         WebResourceError error) {
                if (request.isForMainFrame()) {
                    Log.e(TAG, "WebView error: " + error.getDescription());
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient());

        root.addView(webView);
        setContentView(root);
    }

    private void loadForm() {
        webView.loadUrl("http://localhost:" + PROXY_PORT + "/");
    }

    private void showServerSettings() {
        EditText input = new EditText(this);
        input.setText(serverAddress);
        input.setHint("192.168.1.100:5000");
        input.setGravity(Gravity.CENTER);
        input.setTextDirection(View.TEXT_DIRECTION_LTR);
        int pad = (int) (16 * getResources().getDisplayMetrics().density);
        input.setPadding(pad, pad, pad, pad);

        new AlertDialog.Builder(this)
                .setTitle("عنوان السرفر")
                .setMessage("أدخل عنوان IP والمنفذ للسرفر")
                .setView(input)
                .setPositiveButton("حفظ", (dialog, which) -> {
                    String newAddr = input.getText().toString().trim();
                    if (!newAddr.isEmpty()) {
                        serverAddress = newAddr;
                        getSharedPreferences(PREFS, MODE_PRIVATE)
                                .edit().putString(KEY_SERVER, newAddr).apply();

                        String base = newAddr;
                        if (!base.startsWith("http")) base = "http://" + base;
                        proxy.setServerBase(base);

                        // Update title
                        View bar = ((ViewGroup) webView.getParent()).findViewWithTag("topBar");
                        if (bar != null) {
                            TextView t = bar.findViewWithTag("titleText");
                            if (t != null) t.setText("حقنا — " + newAddr);
                        }

                        Toast.makeText(this,
                                "تم تغيير السرفر إلى: " + newAddr, Toast.LENGTH_SHORT).show();
                    }
                })
                .setNegativeButton("إلغاء", null)
                .show();
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (proxy != null) {
            proxy.stop();
        }
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
