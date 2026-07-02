package com.plateagent.controller;

import com.plateagent.config.JwtUtil;
import com.plateagent.service.DTO;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final JwtUtil jwtUtil;
    private final PasswordEncoder passwordEncoder;

    // 简化版：硬编码管理员账号（生产环境应查数据库）
    private static final String ADMIN_USER = "admin";
    private static final String ADMIN_PASS_HASH = "$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy"; // password

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody DTO.LoginRequest request) {
        if (!ADMIN_USER.equals(request.getUsername())) {
            return ResponseEntity.status(401).body(Map.of("error", "用户名或密码错误"));
        }
        if (!passwordEncoder.matches(request.getPassword(), ADMIN_PASS_HASH)) {
            return ResponseEntity.status(401).body(Map.of("error", "用户名或密码错误"));
        }
        String token = jwtUtil.generateToken(request.getUsername());
        return ResponseEntity.ok(DTO.LoginResponse.builder()
                .token(token)
                .username(request.getUsername())
                .build());
    }
}