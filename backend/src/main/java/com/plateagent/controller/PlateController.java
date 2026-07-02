package com.plateagent.controller;

import com.plateagent.entity.PlateRecord;
import com.plateagent.service.DTO;
import com.plateagent.service.PlateRecordService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/records")
@RequiredArgsConstructor
public class PlateController {

    private final PlateRecordService service;

    /** 分页查询识别记录 */
    @GetMapping
    public ResponseEntity<Page<PlateRecord>> list(
            @RequestParam(required = false) String plate,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ResponseEntity.ok(service.listRecords(plate, status, page, size));
    }

    /** 单条详情 */
    @GetMapping("/{id}")
    public ResponseEntity<PlateRecord> getById(@PathVariable Long id) {
        return service.getById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /** 黑名单记录 */
    @GetMapping("/blacklist")
    public ResponseEntity<Page<PlateRecord>> blacklist(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ResponseEntity.ok(service.listBlacklist(page, size));
    }

    /** 今日统计 */
    @GetMapping("/stats/today")
    public ResponseEntity<DTO.PlateStats> todayStats() {
        return ResponseEntity.ok(service.getTodayStats());
    }

    /** 小时分布 */
    @GetMapping("/stats/hourly")
    public ResponseEntity<List<DTO.HourlyStat>> hourlyStats() {
        return ResponseEntity.ok(service.getHourlyStats());
    }

    /** 健康检查 */
    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "UP", "service", "plate-agent-backend"));
    }
}