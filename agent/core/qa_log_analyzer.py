#!/usr/bin/env python3
"""
QA System Logger - 完善的日志查询和分析系统
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict


class QALogAnalyzer:
    """QA 日志分析器"""
    
    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file or self._find_log_file()
        self.logs: List[Dict[str, Any]] = []
        self.trace_map: Dict[str, List[Dict]] = defaultdict(list)
        
    def _find_log_file(self) -> Optional[str]:
        """自动查找日志文件"""
        possible_paths = [
            "logs/qa_system.jsonl",
            "data/qa_logs.jsonl",
            "qa_logs.jsonl",
        ]
        for path in possible_paths:
            if Path(path).exists():
                return path
        return None
    
    def load_logs(self, limit: Optional[int] = None) -> int:
        """加载日志文件"""
        if not self.log_file or not Path(self.log_file).exists():
            return 0
            
        count = 0
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if limit and count >= limit:
                    break
                try:
                    log = json.loads(line.strip())
                    self.logs.append(log)
                    
                    # 按 trace_id 分组
                    trace_id = log.get('trace_id') or log.get('context', {}).get('trace_id')
                    if trace_id:
                        self.trace_map[trace_id].append(log)
                    
                    count += 1
                except json.JSONDecodeError:
                    continue
        
        return count
    
    def analyze_trace(self, trace_id: str) -> Dict[str, Any]:
        """分析单个 trace 的完整流程"""
        logs = self.trace_map.get(trace_id, [])
        if not logs:
            return {"error": "Trace not found"}
        
        analysis = {
            "trace_id": trace_id,
            "total_logs": len(logs),
            "duration_ms": 0,
            "route": None,
            "agents": [],
            "tools": [],
            "errors": [],
        }
        
        for log in logs:
            # 提取路由信息
            if log.get('event_type') == 'router_decision':
                analysis['route'] = log.get('context', {}).get('route')
            
            # 提取 Agent 调用
            if log.get('event_type') == 'agent_step':
                agent_name = log.get('context', {}).get('agent_name')
                if agent_name and agent_name not in analysis['agents']:
                    analysis['agents'].append(agent_name)
            
            # 提取 Tool 调用
            if log.get('event_type') == 'tool_call':
                tool_name = log.get('context', {}).get('tool_name')
                if tool_name and tool_name not in analysis['tools']:
                    analysis['tools'].append(tool_name)
            
            # 收集错误
            if log.get('level') in ['ERROR', 'CRITICAL']:
                analysis['errors'].append({
                    "timestamp": log.get('timestamp'),
                    "message": log.get('message'),
                    "context": log.get('context'),
                })
        
        # 计算持续时间
        if len(logs) >= 2:
            start = logs[0].get('timestamp', '')
            end = logs[-1].get('timestamp', '')
            try:
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                analysis['duration_ms'] = (end_dt - start_dt).total_seconds() * 1000
            except:
                pass
        
        return analysis
    
    def find_failed_requests(self) -> List[Dict[str, Any]]:
        """查找失败的请求"""
        failed = []
        
        for trace_id, logs in self.trace_map.items():
            has_error = any(
                log.get('level') in ['ERROR', 'CRITICAL'] 
                for log in logs
            )
            
            if has_error:
                analysis = self.analyze_trace(trace_id)
                failed.append(analysis)
        
        return failed
    
    def get_slow_requests(self, threshold_ms: float = 5000.0) -> List[Dict[str, Any]]:
        """获取慢请求"""
        slow = []
        
        for trace_id in self.trace_map.keys():
            analysis = self.analyze_trace(trace_id)
            if analysis.get('duration_ms', 0) > threshold_ms:
                slow.append(analysis)
        
        return slow


# 便捷函数
def analyze_qa_logs(log_file: Optional[str] = None, trace_id: Optional[str] = None) -> Dict[str, Any]:
    """便捷的日志分析函数"""
    analyzer = QALogAnalyzer(log_file)
    count = analyzer.load_logs()
    
    if trace_id:
        return analyzer.analyze_trace(trace_id)
    
    return {
        "total_logs": count,
        "total_traces": len(analyzer.trace_map),
        "failed_requests": len(analyzer.find_failed_requests()),
        "slow_requests": len(analyzer.get_slow_requests()),
    }


if __name__ == "__main__":
    # 示例：分析日志
    import sys
    
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
        trace_id = sys.argv[2] if len(sys.argv) > 2 else None
        
        result = analyze_qa_logs(log_file, trace_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Usage: python -m agent.core.qa_log_analyzer <log_file> [trace_id]")
