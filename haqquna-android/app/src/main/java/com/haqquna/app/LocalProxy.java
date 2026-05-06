package com.haqquna.app;

import android.content.Context;
import android.util.Log;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import fi.iki.elonen.NanoHTTPD;

public class LocalProxy extends NanoHTTPD {

    private static final String TAG = "LocalProxy";
    private final Context context;
    private String serverBase;

    public LocalProxy(Context context, int port, String serverBase) {
        super(port);
        this.context = context;
        this.serverBase = serverBase;
    }

    public void setServerBase(String serverBase) {
        this.serverBase = serverBase;
    }

    public String getServerBase() {
        return serverBase;
    }

    @Override
    public Response serve(IHTTPSession session) {
        String uri = session.getUri();
        Method method = session.getMethod();

        // Serve the offline form HTML from assets
        if ("/".equals(uri) || "/offline-form/app".equals(uri)) {
            return serveAsset("offline_entry.html", "text/html");
        }

        // Serve sync receiver from assets
        if ("/offline-form/sync-receiver".equals(uri)) {
            return serveAsset("sync_receiver.html", "text/html");
        }

        // Proxy all /api/sync/* requests to the real server
        if (uri.startsWith("/api/sync/")) {
            return proxyToServer(session, uri);
        }

        return newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "Not Found");
    }

    private Response serveAsset(String filename, String mimeType) {
        try {
            InputStream is = context.getAssets().open(filename);
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] tmp = new byte[8192];
            int n;
            while ((n = is.read(tmp)) != -1) buf.write(tmp, 0, n);
            is.close();
            byte[] data = buf.toByteArray();
            return newFixedLengthResponse(Response.Status.OK, mimeType,
                    new ByteArrayInputStream(data), data.length);
        } catch (IOException e) {
            Log.e(TAG, "Asset not found: " + filename, e);
            return newFixedLengthResponse(Response.Status.INTERNAL_ERROR,
                    "text/plain", "Asset not found: " + filename);
        }
    }

    private Response proxyToServer(IHTTPSession session, String uri) {
        String targetUrl = serverBase + uri;
        String query = session.getQueryParameterString();
        if (query != null && !query.isEmpty()) {
            targetUrl += "?" + query;
        }

        HttpURLConnection conn = null;
        try {
            // Read request body if present
            byte[] body = null;
            String contentLenStr = session.getHeaders().get("content-length");
            if (contentLenStr != null) {
                int contentLength = Integer.parseInt(contentLenStr);
                if (contentLength > 0) {
                    body = new byte[contentLength];
                    InputStream is = session.getInputStream();
                    int totalRead = 0;
                    while (totalRead < contentLength) {
                        int read = is.read(body, totalRead, contentLength - totalRead);
                        if (read == -1) break;
                        totalRead += read;
                    }
                }
            }

            conn = (HttpURLConnection) new URL(targetUrl).openConnection();
            conn.setRequestMethod(session.getMethod().name());
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(60000);
            conn.setInstanceFollowRedirects(true);

            // Forward relevant headers
            Map<String, String> reqHeaders = session.getHeaders();
            String[] forwardHeaders = {
                "content-type", "x-sync-user", "x-sync-pass",
                "accept", "x-requested-with"
            };
            for (String h : forwardHeaders) {
                String val = reqHeaders.get(h);
                if (val != null) {
                    conn.setRequestProperty(h, val);
                }
            }

            // Send body
            if (body != null && body.length > 0) {
                conn.setDoOutput(true);
                OutputStream os = conn.getOutputStream();
                os.write(body);
                os.flush();
                os.close();
            }

            // Read response
            int status = conn.getResponseCode();
            InputStream respStream;
            try {
                respStream = conn.getInputStream();
            } catch (IOException e) {
                respStream = conn.getErrorStream();
            }

            byte[] respBody = new byte[0];
            if (respStream != null) {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] tmp = new byte[8192];
                int n;
                while ((n = respStream.read(tmp)) != -1) buf.write(tmp, 0, n);
                respStream.close();
                respBody = buf.toByteArray();
            }

            String respContentType = conn.getContentType();
            if (respContentType == null) respContentType = "application/json";

            Response.IStatus respStatus;
            switch (status) {
                case 200: respStatus = Response.Status.OK; break;
                case 201: respStatus = Response.Status.CREATED; break;
                case 204: respStatus = Response.Status.NO_CONTENT; break;
                case 400: respStatus = Response.Status.BAD_REQUEST; break;
                case 401: respStatus = Response.Status.UNAUTHORIZED; break;
                case 403: respStatus = Response.Status.FORBIDDEN; break;
                case 404: respStatus = Response.Status.NOT_FOUND; break;
                case 500: respStatus = Response.Status.INTERNAL_ERROR; break;
                default: respStatus = Response.Status.OK; break;
            }

            return newFixedLengthResponse(respStatus, respContentType,
                    new ByteArrayInputStream(respBody), respBody.length);

        } catch (IOException e) {
            Log.e(TAG, "Proxy error: " + targetUrl, e);
            String errorJson = "{\"success\":false,\"error\":\"" +
                    e.getMessage().replace("\"", "'") + "\"}";
            return newFixedLengthResponse(Response.Status.BAD_GATEWAY,
                    "application/json", errorJson);
        } finally {
            if (conn != null) conn.disconnect();
        }
    }
}
