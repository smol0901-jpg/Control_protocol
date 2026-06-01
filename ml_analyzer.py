"""
ML анализатор для определения процессов, которые можно безопасно завершить
"""
import json
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import defaultdict, deque
import threading
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
import joblib
import psutil


class ProcessAnalyzer:
    """ML анализатор процессов"""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.model_path = self.config_dir / "ml_model.pkl"
        self.scaler_path = self.config_dir / "scaler.pkl"
        self.history_path = self.config_dir / "process_history.json"
        self.training_data_path = self.config_dir / "training_data.json"
        
        # История процессов
        self.process_history = deque(maxlen=10000)
        self.training_data = []
        
        # Загрузка данных
        self._load_data()
        
        # ML модели
        self.classifier = None
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        
        # Определяем множества ДО вызова _create_initial_model
        self.system_processes = {
            'System', 'Registry', 'smss.exe', 'csrss.exe', 
            'wininit.exe', 'services.exe', 'lsass.exe',
            'svchost.exe', 'explorer.exe', 'dwm.exe'
        }
        
        self.safe_to_kill_dev = {
            'node.exe', 'npm.exe', 'npx.exe', 'yarn.exe',
            'pip.exe',
            'powershell.exe', 'pwsh.exe', 'cmd.exe',
            'conhost.exe', 'java.exe', 'javac.exe',
            'gradle.exe', 'maven.exe', 'webpack.exe'
        }
        
        # Загрузка или создание модели
        if self.model_path.exists():
            self._load_model()
        else:
            self._create_initial_model()
        
        # Счетчики для обучения
        self.kill_success_count = defaultdict(int)
        self.kill_failure_count = defaultdict(int)
        
        # Поток для периодического обучения
        self.training_thread = None
        self.start_auto_training()
    
    def _load_data(self):
        """Загрузка исторических данных"""
        if self.history_path.exists():
            try:
                with open(self.history_path, 'r') as f:
                    data = json.load(f)
                    self.process_history.extend(data)
            except:
                pass
        
        if self.training_data_path.exists():
            try:
                with open(self.training_data_path, 'r') as f:
                    self.training_data = json.load(f)
            except:
                pass
    
    def _save_data(self):
        """Сохранение данных"""
        try:
            with open(self.history_path, 'w') as f:
                json.dump(list(self.process_history), f)
            
            with open(self.training_data_path, 'w') as f:
                json.dump(self.training_data, f)
        except:
            pass
    
    def _create_initial_model(self):
        """Создание начальной модели"""
        print("Создание начальной ML модели...")
        
        # Создаем простую модель
        self.classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        
        # Создаем начальные тренировочные данные
        self._generate_initial_training_data()
        self._train_model()
        self._save_model()
    
    def _generate_initial_training_data(self):
        """Генерация начальных тренировочных данных"""
        # Симулируем данные на основе известных паттернов
        initial_data = []
        
        # Безопасные для завершения процессы
        for proc_name in self.safe_to_kill_dev:
            for _ in range(50):
                features = self._generate_process_features(proc_name, is_safe=True)
                features['safe_to_kill'] = 1
                initial_data.append(features)
        
        # Системные процессы (нельзя завершать)
        for proc_name in list(self.system_processes)[:10]:
            for _ in range(50):
                features = self._generate_process_features(proc_name, is_safe=False)
                features['safe_to_kill'] = 0
                initial_data.append(features)
        
        self.training_data = initial_data
        self._save_data()
    
    def _generate_process_features(self, process_name: str, is_safe: bool) -> Dict:
        """Генерация признаков процесса"""
        if is_safe:
            memory = np.random.normal(300, 200)
            cpu = np.random.normal(20, 15)
            thread_count = np.random.randint(2, 10)
            handle_count = np.random.randint(100, 500)
            uptime_seconds = np.random.randint(60, 3600)
        else:
            memory = np.random.normal(50, 30)
            cpu = np.random.normal(2, 1)
            thread_count = np.random.randint(5, 20)
            handle_count = np.random.randint(200, 1000)
            uptime_seconds = np.random.randint(3600, 86400)
        
        return {
            'process_name': process_name,
            'memory_mb': max(0, memory),
            'cpu_percent': max(0, min(100, cpu)),
            'thread_count': thread_count,
            'handle_count': handle_count,
            'uptime_seconds': uptime_seconds,
            'is_system_process': 1 if process_name in self.system_processes else 0,
            'is_dev_tool': 1 if process_name in self.safe_to_kill_dev else 0,
            'memory_growth_rate': np.random.normal(0.1, 0.05) if is_safe else 0,
        }
    
    def _extract_features(self, proc: psutil.Process) -> Optional[Dict]:
        """Извлечение признаков из реального процесса"""
        try:
            name = proc.name().lower()
            
            # Базовая информация
            memory = proc.memory_info().rss / 1024 / 1024
            cpu = proc.cpu_percent(interval=0.1)
            
            # Дополнительные метрики
            try:
                threads = proc.num_threads()
                handles = proc.num_handles() if hasattr(proc, 'num_handles') else 0
            except:
                threads = 0
                handles = 0
            
            # Время работы
            try:
                create_time = proc.create_time()
                uptime = time.time() - create_time
            except:
                uptime = 0
            
            # Проверяем историю
            history = self._get_process_history(proc.pid)
            
            # Расчет скорости роста памяти
            memory_growth = 0
            if history:
                memory_growth = (memory - history[-1]['memory_mb']) / max(1, len(history))
            
            return {
                'process_name': name,
                'memory_mb': memory,
                'cpu_percent': cpu,
                'thread_count': threads,
                'handle_count': handles,
                'uptime_seconds': uptime,
                'is_system_process': 1 if name in self.system_processes else 0,
                'is_dev_tool': 1 if name in self.safe_to_kill_dev else 0,
                'memory_growth_rate': memory_growth,
            }
        except:
            return None
    
    def _get_process_history(self, pid: int) -> List[Dict]:
        """Получение истории процесса"""
        return [
            h for h in self.process_history 
            if h.get('pid') == pid
        ][-10:]  # Последние 10 записей
    
    def _train_model(self):
        """Обучение модели"""
        if len(self.training_data) < 10:
            return
        
        try:
            # Подготовка данных
            df = pd.DataFrame(self.training_data)
            
            # Кодирование имен процессов
            process_names = df['process_name'].values
            name_features = self._encode_process_names(process_names)
            
            # Числовые признаки
            numeric_features = df[[
                'memory_mb', 'cpu_percent', 'thread_count',
                'handle_count', 'uptime_seconds', 
                'is_system_process', 'is_dev_tool',
                'memory_growth_rate'
            ]].values
            
            # Объединяем признаки
            X = np.hstack([numeric_features, name_features])
            y = df['safe_to_kill'].values
            
            # Разделение данных
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Масштабирование
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Обучение ансамбля моделей
            rf_model = RandomForestClassifier(
                n_estimators=200,
                max_depth=15,
                min_samples_split=5,
                random_state=42,
                n_jobs=-1
            )
            
            gb_model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
            
            # Обучение
            rf_model.fit(X_train_scaled, y_train)
            gb_model.fit(X_train_scaled, y_train)
            
            # Оценка
            rf_score = rf_model.score(X_test_scaled, y_test)
            gb_score = gb_model.score(X_test_scaled, y_test)
            
            print(f"Random Forest точность: {rf_score:.2%}")
            print(f"Gradient Boosting точность: {gb_score:.2%}")
            
            # Используем лучшую модель
            if rf_score >= gb_score:
                self.classifier = rf_model
            else:
                self.classifier = gb_model
            
            # Кросс-валидация
            cv_scores = cross_val_score(
                self.classifier, 
                self.scaler.transform(X), 
                y, 
                cv=5
            )
            print(f"Кросс-валидация: {cv_scores.mean():.2%} (+/- {cv_scores.std() * 2:.2%})")
            
        except Exception as e:
            print(f"Ошибка обучения модели: {e}")
    
    def _encode_process_names(self, names: np.ndarray) -> np.ndarray:
        """Кодирование имен процессов"""
        # Простое one-hot кодирование для известных процессов
        known_processes = list(self.system_processes) + list(self.safe_to_kill_dev)
        
        features = np.zeros((len(names), 2))  # 2 признака: системный и dev-инструмент
        
        for i, name in enumerate(names):
            if name in self.system_processes:
                features[i, 0] = 1
            if name in self.safe_to_kill_dev:
                features[i, 1] = 1
        
        return features
    
    def _save_model(self):
        """Сохранение модели"""
        try:
            if self.classifier:
                joblib.dump(self.classifier, self.model_path)
                joblib.dump(self.scaler, self.scaler_path)
                print("Модель сохранена")
        except Exception as e:
            print(f"Ошибка сохранения модели: {e}")
    
    def _load_model(self):
        """Загрузка модели"""
        try:
            self.classifier = joblib.load(self.model_path)
            self.scaler = joblib.load(self.scaler_path)
            print("Модель загружена")
        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
            self._create_initial_model()
    
    def predict_safe_to_kill(self, proc: psutil.Process) -> Tuple[bool, float, Dict]:
        """
        Предсказание безопасности завершения процесса
        Возвращает: (безопасно_ли, уверенность, детали)
        """
        # Системные процессы никогда не трогаем
        if proc.name().lower() in self.system_processes:
            return False, 1.0, {'reason': 'Системный процесс'}
        
        # Извлекаем признаки
        features = self._extract_features(proc)
        if not features:
            return False, 0.0, {'reason': 'Нет данных'}
        
        # Сохраняем в историю
        self.process_history.append({
            'pid': proc.pid,
            'name': proc.name(),
            'memory_mb': features['memory_mb'],
            'timestamp': datetime.now().isoformat()
        })
        
        # Если нет модели, используем эвристики
        if self.classifier is None:
            return self._heuristic_prediction(features)
        
        try:
            # Подготовка признаков
            process_names = np.array([features['process_name']])
            name_features = self._encode_process_names(process_names)
            
            numeric_features = np.array([[
                features['memory_mb'],
                features['cpu_percent'],
                features['thread_count'],
                features['handle_count'],
                features['uptime_seconds'],
                features['is_system_process'],
                features['is_dev_tool'],
                features['memory_growth_rate']
            ]])
            
            X = np.hstack([numeric_features, name_features])
            X_scaled = self.scaler.transform(X)
            
            # Предсказание
            prediction = self.classifier.predict(X_scaled)[0]
            probabilities = self.classifier.predict_proba(X_scaled)[0]
            
            is_safe = bool(prediction)
            confidence = float(max(probabilities))
            
            details = {
                'prediction': 'Безопасно' if is_safe else 'Опасно',
                'confidence': confidence,
                'safe_probability': float(probabilities[1]) if len(probabilities) > 1 else 0,
                'features': features,
                'process_info': {
                    'name': proc.name(),
                    'pid': proc.pid,
                    'memory_mb': features['memory_mb'],
                    'cpu_percent': features['cpu_percent']
                }
            }
            
            return is_safe, confidence, details
            
        except Exception as e:
            print(f"Ошибка предсказания: {e}")
            return self._heuristic_prediction(features)
    
    def _heuristic_prediction(self, features: Dict) -> Tuple[bool, float, Dict]:
        """Эвристическое предсказание без модели"""
        score = 0
        
        # Dev-инструменты обычно безопасны
        if features['is_dev_tool']:
            score += 0.4
        
        # Маленькое потребление памяти - безопасно
        if features['memory_mb'] < 100:
            score += 0.2
        elif features['memory_mb'] > 2000:
            score -= 0.3
        
        # Низкая загрузка CPU - безопасно
        if features['cpu_percent'] < 10:
            score += 0.1
        elif features['cpu_percent'] > 80:
            score -= 0.2
        
        # Долго работает - может быть важным
        if features['uptime_seconds'] > 3600:
            score -= 0.1
        
        # Системные процессы - нельзя
        if features['is_system_process']:
            score = -1
        
        is_safe = score > 0.3
        confidence = min(abs(score), 1.0)
        
        details = {
            'prediction': 'Безопасно (эвристика)' if is_safe else 'Опасно (эвристика)',
            'confidence': confidence,
            'score': score,
            'features': features
        }
        
        return is_safe, confidence, details
    
    def add_training_example(self, proc_name: str, features: Dict, 
                           was_safe: bool, system_stable: bool):
        """Добавление примера для обучения"""
        training_example = {
            **features,
            'safe_to_kill': 1 if (was_safe and system_stable) else 0,
            'timestamp': datetime.now().isoformat()
        }
        
        self.training_data.append(training_example)
        
        # Ограничиваем размер
        if len(self.training_data) > 10000:
            self.training_data = self.training_data[-10000:]
        
        self._save_data()
    
    def start_auto_training(self):
        """Запуск автоматического обучения"""
        def trainer():
            while True:
                time.sleep(3600)  # Каждый час
                if len(self.training_data) > 100:
                    print("Автоматическое обучение модели...")
                    self._train_model()
                    self._save_model()
        
        self.training_thread = threading.Thread(target=trainer, daemon=True)
        self.training_thread.start()
    
    def get_model_stats(self) -> Dict:
        """Получение статистики модели"""
        return {
            'training_samples': len(self.training_data),
            'history_size': len(self.process_history),
            'model_type': type(self.classifier).__name__ if self.classifier else 'Heuristic',
            'features_used': 10,
            'last_training': datetime.now().isoformat(),
        }


class ProcessMonitor:
    """Монитор процессов с ML анализом"""
    
    def __init__(self, analyzer: ProcessAnalyzer):
        self.analyzer = analyzer
        self.monitored_processes = {}
        self.kill_history = []
    
    def scan_processes(self) -> List[Dict]:
        """Сканирование и анализ процессов"""
        results = []
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                # Анализируем процесс
                is_safe, confidence, details = self.analyzer.predict_safe_to_kill(proc)
                
                if is_safe and confidence > 0.6:  # Порог уверенности
                    proc_info = {
                        'pid': proc.pid,
                        'name': proc.name(),
                        'memory_mb': proc.memory_info().rss / 1024 / 1024,
                        'cpu_percent': proc.cpu_percent(),
                        'safe_to_kill': is_safe,
                        'confidence': confidence,
                        'details': details
                    }
                    results.append(proc_info)
                    
                    # Обновляем мониторинг
                    self.monitored_processes[proc.pid] = proc_info
            
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Сортируем по использованию памяти
        results.sort(key=lambda x: x['memory_mb'], reverse=True)
        
        return results
    
    def kill_process(self, pid: int) -> Tuple[bool, str]:
        """Завершение процесса с записью результата"""
        try:
            proc = psutil.Process(pid)
            proc_info = self.monitored_processes.get(pid, {})
            
            # Завершаем процесс
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            
            # Проверяем стабильность системы после убийства
            time.sleep(1)
            system_stable = self._check_system_stability()
            
            # Добавляем в обучение
            if proc_info:
                features = proc_info.get('details', {}).get('features', {})
                self.analyzer.add_training_example(
                    proc.name(),
                    features,
                    was_safe=True,
                    system_stable=system_stable
                )
            
            # Записываем в историю
            self.kill_history.append({
                'pid': pid,
                'name': proc.name(),
                'timestamp': datetime.now().isoformat(),
                'success': True,
                'system_stable': system_stable
            })
            
            return True, "Процесс успешно завершен"
            
        except Exception as e:
            return False, f"Ошибка: {str(e)}"
    
    def _check_system_stability(self) -> bool:
        """Проверка стабильности системы"""
        try:
            # Проверяем, что explorer работает
            for proc in psutil.process_iter(['name']):
                if proc.name() == 'explorer.exe':
                    return True
            
            # Проверяем общую стабильность
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory().percent
            
            return cpu < 100 and mem < 95
        except:
            return True

