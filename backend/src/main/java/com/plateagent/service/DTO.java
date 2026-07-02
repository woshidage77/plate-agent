package com.plateagent.service;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

public class DTO {

    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class LoginRequest {
        private String username;
        private String password;
    }

    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class LoginResponse {
        private String token;
        private String username;
    }

    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class PlateStats {
        private long totalRecognitions;
        private long successCount;
        private long partialCount;
        private long failedCount;
        private long blacklistHits;
        private double avgConfidence;
        private double avgProcessTimeMs;
    }

    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class HourlyStat {
        private int hour;
        private long count;
    }
}