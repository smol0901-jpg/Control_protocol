"""
Генератор PDF отчетов с графиками и статистикой
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import io
import base64
import os
import reportlab

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether
)
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import qrcode

# Регистрируем шрифт с поддержкой кириллицы (Arial из системных шрифтов)
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Используем Arial, который есть в любой Windows
arial_path = "C:\\Windows\\Fonts\\arial.ttf"
try:
    pdfmetrics.registerFont(TTFont('Arial', arial_path))
    DEFAULT_FONT = 'Arial'
except Exception as e:
    # Если Arial не найден, оставляем стандартный шрифт (без кириллицы)
    DEFAULT_FONT = 'Helvetica'
    print(f"Предупреждение: Не удалось загрузить Arial: {e}")
    print("Кириллица в PDF может отображаться некорректно.")

class PDFReporter:
    """Генератор PDF отчетов"""
    
    def __init__(self, reports_dir: Path):
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Настройка стилей
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
        
        # Цветовая схема
        self.colors = {
            'primary': colors.HexColor('#2C3E50'),
            'secondary': colors.HexColor('#3498DB'),
            'success': colors.HexColor('#27AE60'),
            'danger': colors.HexColor('#E74C3C'),
            'warning': colors.HexColor('#F39C12'),
            'info': colors.HexColor('#1ABC9C'),
            'light': colors.HexColor('#ECF0F1'),
            'dark': colors.HexColor('#2C3E50'),
        }
    
    def _create_custom_styles(self):
        """Создание пользовательских стилей"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontName='Arial',
            fontSize=24,
            textColor=colors.HexColor('#2C3E50'),
            spaceAfter=30,
            alignment=TA_CENTER,
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading1',
            parent=self.styles['Heading1'],
            fontName='Arial',
            fontSize=18,
            textColor=colors.HexColor('#2C3E50'),
            spaceAfter=12,
            spaceBefore=20,
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontName='Arial',
            fontSize=14,
            textColor=colors.HexColor('#3498DB'),
            spaceAfter=8,
            spaceBefore=15,
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['BodyText'],
            fontName='Arial',
            fontSize=10,
            textColor=colors.HexColor('#34495E'),
            spaceAfter=6,
            alignment=TA_JUSTIFY,
        ))
        
        self.styles.add(ParagraphStyle(
            name='SmallNote',
            parent=self.styles['BodyText'],
            fontName='Arial',
            fontSize=8,
            textColor=colors.HexColor('#7F8C8D'),
            spaceAfter=4,
        ))
    
    def generate_report(self, stats: Dict, processes: List[Dict], 
                       ml_stats: Dict, user_info: Dict,
                       report_type: str = "daily") -> Path:
        """
        Генерация полного отчета
        
        Args:
            stats: Статистика системы
            processes: Список процессов
            ml_stats: Статистика ML модели
            user_info: Информация о пользователе
            report_type: Тип отчета (daily, weekly, monthly)
        
        Returns:
            Path: Путь к созданному PDF файлу
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"DevCleaner_{report_type}_{timestamp}.pdf"
        filepath = self.reports_dir / filename
        
        # Создаем PDF
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm,
            title=f"DevCleaner Report - {report_type.upper()}",
            author="DevCleaner Pro"
        )
        
        # Собираем контент
        story = []
        
        # Титульная страница
        story.extend(self._create_cover_page(report_type, user_info))
        story.append(PageBreak())
        
        # Оглавление
        story.extend(self._create_toc())
        story.append(PageBreak())
        
        # Общая статистика
        story.extend(self._create_overview_section(stats))
        story.append(PageBreak())
        
        # Анализ процессов
        story.extend(self._create_process_analysis(processes))
        story.append(PageBreak())
        
        # ML анализ
        story.extend(self._create_ml_section(ml_stats))
        story.append(PageBreak())
        
        # Графики
        story.extend(self._create_charts_section(stats, processes))
        story.append(PageBreak())
        
        # Рекомендации
        story.extend(self._create_recommendations(processes, ml_stats))
        
        # QR код для быстрого доступа
        story.extend(self._create_qr_section())
        
        # Футер
        story.extend(self._create_footer())
        
        # Сборка PDF
        doc.build(story, onFirstPage=self._add_page_number, 
                 onLaterPages=self._add_page_number)
        
        return filepath
    
    def _create_cover_page(self, report_type: str, user_info: Dict) -> List:
        """Создание титульной страницы"""
        elements = []
        
        # Логотип (текстовый)
        elements.append(Spacer(1, 50*mm))
        elements.append(Paragraph("DevCleaner Pro", self.styles['CustomTitle']))
        elements.append(Spacer(1, 10*mm))
        
        # Линия
        elements.append(HRFlowable(
            width="80%", 
            thickness=2, 
            color=self.colors['secondary']
        ))
        elements.append(Spacer(1, 10*mm))
        
        # Тип отчета
        report_names = {
            'daily': 'ЕЖЕДНЕВНЫЙ ОТЧЕТ',
            'weekly': 'ЕЖЕНЕДЕЛЬНЫЙ ОТЧЕТ',
            'monthly': 'ЕЖЕМЕСЯЧНЫЙ ОТЧЕТ'
        }
        elements.append(Paragraph(
            report_names.get(report_type, 'ОТЧЕТ'),
            self.styles['CustomHeading1']
        ))
        elements.append(Spacer(1, 5*mm))
        
        # Дата
        elements.append(Paragraph(
            f"Дата создания: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            self.styles['CustomBody']
        ))
        elements.append(Paragraph(
            f"Период: {(datetime.now() - timedelta(days=1)).strftime('%d.%m.%Y')} - "
            f"{datetime.now().strftime('%d.%m.%Y')}",
            self.styles['CustomBody']
        ))
        elements.append(Spacer(1, 10*mm))
        
        # Информация о пользователе
        elements.append(Paragraph("Информация о пользователе:", self.styles['CustomHeading2']))
        elements.append(Paragraph(
            f"Пользователь: {user_info.get('username', 'N/A')}",
            self.styles['CustomBody']
        ))
        elements.append(Paragraph(
            f"Роль: {user_info.get('role', 'N/A')}",
            self.styles['CustomBody']
        ))
        
        elements.append(Spacer(1, 20*mm))
        elements.append(Paragraph(
            "Конфиденциальный документ",
            self.styles['SmallNote']
        ))
        
        return elements
    
    def _create_toc(self) -> List:
        """Создание оглавления"""
        elements = []
        elements.append(Paragraph("СОДЕРЖАНИЕ", self.styles['CustomHeading1']))
        elements.append(Spacer(1, 10*mm))
        
        sections = [
            ("1.", "Общая статистика системы"),
            ("2.", "Анализ процессов разработки"),
            ("3.", "Машинное обучение и предиктивная аналитика"),
            ("4.", "Графики и визуализация"),
            ("5.", "Рекомендации по оптимизации"),
            ("6.", "QR код быстрого доступа"),
        ]
        
        for num, title in sections:
            elements.append(Paragraph(
                f"{num} {title}",
                self.styles['CustomBody']
            ))
            elements.append(Spacer(1, 3*mm))
        
        return elements
    
    def _create_overview_section(self, stats: Dict) -> List:
        """Создание секции обзора"""
        elements = []
        elements.append(Paragraph("1. ОБЩАЯ СТАТИСТИКА", self.styles['CustomHeading1']))
        elements.append(Spacer(1, 5*mm))
        
        # Системная информация
        elements.append(Paragraph("Системная информация:", self.styles['CustomHeading2']))
        
        sys_data = [
            ["Параметр", "Значение"],
            ["CPU общий", f"{stats.get('cpu_total', 0):.1f}%"],
            ["Память использовано", f"{stats.get('memory_used_gb', 0):.1f} GB"],
            ["Память всего", f"{stats.get('memory_total_gb', 0):.1f} GB"],
            ["Память %", f"{stats.get('memory_total', 0):.1f}%"],
            ["Процессов убито", str(stats.get('processes_killed', 0))],
            ["Памяти освобождено", f"{stats.get('memory_freed_mb', 0):.0f} MB"],
            ["Кэша очищено", f"{stats.get('cache_cleaned_mb', 0):.0f} MB"],
        ]
        
        t = Table(sys_data, colWidths=[80*mm, 80*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors['primary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors['light']),
            ('GRID', (0, 0), (-1, -1), 1, colors.white),
            ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.colors['light']]),
        ]))
        
        elements.append(t)
        elements.append(Spacer(1, 10*mm))
        
        return elements
    
    def _create_process_analysis(self, processes: List[Dict]) -> List:
        """Анализ процессов"""
        elements = []
        elements.append(Paragraph("2. АНАЛИЗ ПРОЦЕССОВ", self.styles['CustomHeading1']))
        elements.append(Spacer(1, 5*mm))
        
        # Топ-10 процессов по памяти
        elements.append(Paragraph("Топ-10 процессов по использованию памяти:", 
                                self.styles['CustomHeading2']))
        
        proc_data = [["Процесс", "PID", "Память (MB)", "CPU %", "Безопасно"]]
        
        for proc in processes[:10]:
            safe_icon = "✓" if proc.get('safe_to_kill', False) else "✗"
            proc_data.append([
                proc.get('name', 'Unknown'),
                str(proc.get('pid', 0)),
                f"{proc.get('memory_mb', 0):.1f}",
                f"{proc.get('cpu_percent', 0):.1f}",
                safe_icon
            ])
        
        t = Table(proc_data, colWidths=[45*mm, 25*mm, 35*mm, 25*mm, 25*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors['primary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.white),
            ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.colors['light']]),
        ]))
        
        elements.append(t)
        elements.append(Spacer(1, 10*mm))
        
        # Статистика по типам процессов
        elements.append(Paragraph("Распределение по типам:", self.styles['CustomHeading2']))
        
        type_stats = {}
        for proc in processes:
            proc_type = proc.get('type', 'Unknown')
            type_stats[proc_type] = type_stats.get(proc_type, 0) + 1
        
        type_data = [["Тип процесса", "Количество"]]
        for ptype, count in sorted(type_stats.items(), key=lambda x: x[1], reverse=True):
            type_data.append([ptype, str(count)])
        
        t2 = Table(type_data, colWidths=[80*mm, 80*mm])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors['secondary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'),
            ('GRID', (0, 0), (-1, -1), 1, colors.white),
            ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.colors['light']]),
        ]))
        
        elements.append(t2)
        
        return elements
    
    def _create_ml_section(self, ml_stats: Dict) -> List:
        """Секция ML анализа"""
        elements = []
        elements.append(Paragraph("3. МАШИННОЕ ОБУЧЕНИЕ", self.styles['CustomHeading1']))
        elements.append(Spacer(1, 5*mm))
        
        elements.append(Paragraph(
            "DevCleaner использует машинное обучение для определения процессов, "
            "которые можно безопасно завершить. Система обучается на исторических данных "
            "и постоянно улучшает точность предсказаний.",
            self.styles['CustomBody']
        ))
        elements.append(Spacer(1, 5*mm))
        
        # Статистика модели
        ml_data = [
            ["Метрика", "Значение"],
            ["Тип модели", ml_stats.get('model_type', 'N/A')],
            ["Обучающих примеров", str(ml_stats.get('training_samples', 0))],
            ["Размер истории", str(ml_stats.get('history_size', 0))],
            ["Признаков используется", str(ml_stats.get('features_used', 10))],
            ["Последнее обучение", ml_stats.get('last_training', 'N/A')],
        ]
        
        t = Table(ml_data, colWidths=[80*mm, 80*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors['info']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'),
            ('GRID', (0, 0), (-1, -1), 1, colors.white),
            ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.colors['light']]),
        ]))
        
        elements.append(t)
        elements.append(Spacer(1, 10*mm))
        
        # Важность признаков
        elements.append(Paragraph("Важность признаков модели:", self.styles['CustomHeading2']))
        
        features = [
            ("Использование памяти", 0.25),
            ("Загрузка CPU", 0.20),
            ("Тип процесса (dev/системный)", 0.18),
            ("Количество потоков", 0.15),
            ("Время работы", 0.12),
            ("Скорость роста памяти", 0.10),
        ]
        
        feat_data = [["Признак", "Важность"]]
        for name, importance in features:
            feat_data.append([name, f"{importance:.0%}"])
        
        t2 = Table(feat_data, colWidths=[100*mm, 60*mm])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors['warning']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'DejaVu'),
            ('GRID', (0, 0), (-1, -1), 1, colors.white),
            ('FONTNAME', (0, 1), (-1, -1), 'DejaVu'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.colors['light']]),
        ]))
        
        elements.append(t2)
        
        return elements
    
    def _create_charts_section(self, stats: Dict, processes: List[Dict]) -> List:
        """Создание графиков"""
        elements = []
        elements.append(Paragraph("4. ГРАФИКИ И ВИЗУАЛИЗАЦИЯ", self.styles['CustomHeading1']))
        elements.append(Spacer(1, 5*mm))
        
        # График использования памяти процессами
        if processes:
            elements.append(Paragraph("Использование памяти процессами:", 
                                    self.styles['CustomHeading2']))
            
            # Создаем график
            fig, ax = plt.subplots(figsize=(8, 4))
            
            procs = processes[:10]
            names = [p.get('name', 'Unknown')[:15] for p in procs]
            memory = [p.get('memory_mb', 0) for p in procs]
            
            colors_bar = ['#E74C3C' if m > 500 else '#F39C12' if m > 200 else '#3498DB' 
                         for m in memory]
            
            bars = ax.bar(range(len(names)), memory, color=colors_bar, edgecolor='white')
            ax.set_xticks(range(len(names)))
            ax.set_xticklabels(names, rotation=45, ha='right', fontsize=8)
            ax.set_ylabel('Память (MB)', fontsize=10)
            ax.set_title('Топ-10 процессов по использованию памяти', fontsize=12, fontweight='bold')
            ax.grid(axis='y', alpha=0.3)
            
            # Добавляем значения над столбцами
            for bar, mem in zip(bars, memory):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{mem:.0f}',
                       ha='center', va='bottom', fontsize=8)
            
            plt.tight_layout()
            
            # Сохраняем в буфер
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
            img_buffer.seek(0)
            plt.close()
            
            # Добавляем в PDF
            img = Image(img_buffer, width=160*mm, height=80*mm)
            elements.append(img)
            
            elements.append(Spacer(1, 10*mm))
        
        # Круговая диаграмма распределения процессов
        elements.append(Paragraph("Распределение процессов по типу:", 
                                self.styles['CustomHeading2']))
        
        type_stats = {}
        for proc in processes:
            proc_type = proc.get('type', 'Unknown')
            type_stats[proc_type] = type_stats.get(proc_type, 0) + 1
        
        if type_stats:
            fig, ax = plt.subplots(figsize=(6, 4))
            
            labels = list(type_stats.keys())
            sizes = list(type_stats.values())
            colors_pie = ['#3498DB', '#E74C3C', '#2ECC71', '#F39C12', '#9B59B6']
            
            wedges, texts, autotexts = ax.pie(
                sizes, labels=labels, colors=colors_pie[:len(labels)],
                autopct='%1.1f%%', startangle=90,
                textprops={'fontsize': 8}
            )
            
            ax.set_title('Распределение процессов по типу', fontsize=12, fontweight='bold')
            
            plt.tight_layout()
            
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
            img_buffer.seek(0)
            plt.close()
            
            img = Image(img_buffer, width=120*mm, height=80*mm)
            elements.append(img)
        
        return elements
    
    def _create_recommendations(self, processes: List[Dict], ml_stats: Dict) -> List:
        """Создание рекомендаций"""
        elements = []
        elements.append(Paragraph("5. РЕКОМЕНДАЦИИ", self.styles['CustomHeading1']))
        elements.append(Spacer(1, 5*mm))
        
        # Анализ и рекомендации
        heavy_processes = [p for p in processes if p.get('memory_mb', 0) > 500]
        
        recommendations = []
        
        if heavy_processes:
            total_memory = sum(p.get('memory_mb', 0) for p in heavy_processes)
            recommendations.append(
                f"• Обнаружено {len(heavy_processes)} тяжелых процессов, "
                f"потребляющих {total_memory:.0f} MB памяти. "
                f"Рекомендуется завершить неиспользуемые."
            )
        
        if len(processes) > 20:
            recommendations.append(
                f"• Запущено {len(processes)} dev-процессов. "
                f"Рассмотрите возможность закрытия неиспользуемых."
            )
        
        # ML рекомендации
        model_confidence = ml_stats.get('model_confidence', 0)
        if model_confidence < 0.7:
            recommendations.append(
                "• Точность ML модели ниже 70%. Требуется больше данных для обучения."
            )
        
        recommendations.append(
            "• Регулярно очищайте кэш разработки (npm, pip, gradle) для освобождения места."
        )
        recommendations.append(
            "• Настройте авто-завершение процессов в конфигурации для автоматической оптимизации."
        )
        
        for rec in recommendations:
            elements.append(Paragraph(rec, self.styles['CustomBody']))
            elements.append(Spacer(1, 3*mm))
        
        return elements
    
    def _create_qr_section(self) -> List:
        """Создание QR кода"""
        elements = []
        elements.append(Spacer(1, 10*mm))
        elements.append(Paragraph("6. QR КОД БЫСТРОГО ДОСТУПА", self.styles['CustomHeading1']))
        elements.append(Spacer(1, 5*mm))
        
        # Создаем QR код с ссылкой на документацию
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data("https://github.com/devcleaner-pro/documentation")
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="#2C3E50", back_color="white")
        
        # Сохраняем в буфер
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        img = Image(img_buffer, width=60*mm, height=60*mm)
        elements.append(img)
        
        elements.append(Paragraph(
            "Отсканируйте QR код для доступа к документации",
            self.styles['SmallNote']
        ))
        
        return elements
    
    def _create_footer(self) -> List:
        """Создание футера"""
        elements = []
        elements.append(Spacer(1, 20*mm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        elements.append(Spacer(1, 5*mm))
        
        elements.append(Paragraph(
            f"Отчет создан {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} "
            f"с помощью DevCleaner Pro",
            self.styles['SmallNote']
        ))
        elements.append(Paragraph(
            "Конфиденциально • Для внутреннего использования",
            self.styles['SmallNote']
        ))
        
        return elements
    
    @staticmethod
    def _add_page_number(canvas, doc):
        """Добавление номера страницы"""
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        
        # Верхний колонтитул
        canvas.drawString(20*mm, 287*mm, "DevCleaner Pro - Конфиденциальный отчет")
        canvas.drawRightString(190*mm, 287*mm, datetime.now().strftime('%d.%m.%Y'))
        
        # Нижний колонтитул
        canvas.drawCentredString(
            105*mm, 10*mm,
            f"Страница {doc.page}"
        )
        
        canvas.restoreState()
