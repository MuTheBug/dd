package com.haqquna.app.data

import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.PartMap
import retrofit2.http.Url

interface SyncApi {

    @GET
    suspend fun ping(@Url url: String): Response<PingResponse>

    @POST
    @Multipart
    suspend fun login(
        @Url url: String,
        @Header("X-Sync-User") user: String,
        @Header("X-Sync-Pass") pass: String,
        @Part dummy: MultipartBody.Part
    ): Response<LoginResponse>

    @POST
    @Multipart
    suspend fun submitEntry(
        @Url url: String,
        @Header("X-Sync-User") user: String,
        @Header("X-Sync-Pass") pass: String,
        @PartMap textParts: Map<String, @JvmSuppressWildcards RequestBody>,
        @Part files: List<MultipartBody.Part>
    ): Response<SyncEntryResponse>

    @GET
    suspend fun raw(@Url url: String): Response<ResponseBody>
}
