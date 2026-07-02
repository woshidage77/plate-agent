package com.plateagent.service;

import com.plateagent.entity.PlateRecord;
import com.plateagent.repository.PlateRecordRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.*;

@Service
@RequiredArgsConstructor
public class PlateRecordService {

    private final PlateRecordRepository repo;

    public Page<PlateRecord> listRecords(String plate, String status, int page, int size) {
        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        if (plate != null && !plate.isBlank()) {
            return repo.findByPlateNumberContaining(plate, pageable);
        }
        if (status != null && !status.isBlank()) {
            return repo.findByStatus(status, pageable);
        }
        return repo.findAll(pageable);
    }

    public Page<PlateRecord> listBlacklist(int page, int size) {
        return repo.findByBlacklistHitTrue(PageRequest.of(page, size, Sort.by("createdAt").descending()));
    }

    public Optional<PlateRecord> getById(Long id) {
        return repo.findById(id);
    }

    public PlateRecord save(PlateRecord record) {
        return repo.save(record);
    }

    public DTO.PlateStats getTodayStats() {
        LocalDateTime start = LocalDate.now().atStartOfDay();
        LocalDateTime end = LocalDateTime.now();

        long total = repo.countByCreatedAtBetween(start, end);
        long success = repo.countByStatusAndCreatedAtBetween("success", start, end);
        long partial = repo.countByStatusAndCreatedAtBetween("partial", start, end);
        long failed = repo.countByStatusAndCreatedAtBetween("failed", start, end);

        Double avgConf = repo.avgConfidenceBetween(start, end);

        List<PlateRecord> recent = repo.findByCreatedAtBetween(start, end);
        long blacklist = recent.stream().filter(r -> Boolean.TRUE.equals(r.getBlacklistHit())).count();
        double avgTime = recent.stream()
                .filter(r -> r.getProcessTimeMs() != null)
                .mapToLong(PlateRecord::getProcessTimeMs)
                .average().orElse(0);

        return DTO.PlateStats.builder()
                .totalRecognitions(total)
                .successCount(success)
                .partialCount(partial)
                .failedCount(failed)
                .blacklistHits(blacklist)
                .avgConfidence(avgConf != null ? avgConf : 0)
                .avgProcessTimeMs(avgTime)
                .build();
    }

    public List<DTO.HourlyStat> getHourlyStats() {
        LocalDateTime start = LocalDate.now().atStartOfDay();
        LocalDateTime end = LocalDateTime.now();
        List<PlateRecord> records = repo.findByCreatedAtBetween(start, end);

        Map<Integer, Long> hourMap = new TreeMap<>();
        for (int h = 0; h < 24; h++) hourMap.put(h, 0L);
        for (PlateRecord r : records) {
            int hour = r.getCreatedAt().getHour();
            hourMap.merge(hour, 1L, Long::sum);
        }

        List<DTO.HourlyStat> stats = new ArrayList<>();
        hourMap.forEach((h, c) -> stats.add(new DTO.HourlyStat(h, c)));
        return stats;
    }
}