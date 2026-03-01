"""
AuraGrade AI — Research Evaluation Script
==========================================
Generates publication-ready metrics and visualizations for comparing
AI-generated grades against human (professor) grades.

Metrics:
  - Pearson Correlation Coefficient (r)
  - Mean Absolute Error (MAE)
  - Quadratic Weighted Kappa (QWK)

Usage:
  python evaluate_accuracy.py

Output:
  - Console metrics summary
  - correlation_plot.png
  - bland_altman_plot.png
  - confusion_heatmap.png
"""

import pandas as pd
import numpy as np
from scipy.stats import pearsonr
from sklearn.metrics import mean_absolute_error, cohen_kappa_score
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend — saves to file only
import matplotlib.pyplot as plt
import seaborn as sns

# ─── Configuration ────────────────────────────────────────────
# Replace this sample data with your Supabase export (CSV or direct query)
# Export query: SELECT s.reg_no, g.ai_score, g.confidence FROM grades g JOIN students s ON g.student_id = s.id;

data = {
    'student_id': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10'],
    'human_grade': [8.5, 7.0, 9.5, 4.0, 6.5, 5.0, 8.0, 3.5, 7.5, 9.0],
    'ai_grade':    [8.2, 7.5, 9.0, 4.5, 6.0, 5.5, 7.8, 3.0, 7.2, 8.8],
    'confidence':  [0.92, 0.88, 0.95, 0.72, 0.85, 0.78, 0.91, 0.65, 0.87, 0.93]
}

df = pd.DataFrame(data)

# ─── 1. Calculate Research Metrics ────────────────────────────

# Pearson Correlation Coefficient
corr, p_value = pearsonr(df['human_grade'], df['ai_grade'])

# Mean Absolute Error
mae = mean_absolute_error(df['human_grade'], df['ai_grade'])

# Quadratic Weighted Kappa (requires integer rounding)
qwk = cohen_kappa_score(
    np.rint(df['human_grade']).astype(int),
    np.rint(df['ai_grade']).astype(int),
    weights='quadratic'
)

# Additional: Root Mean Square Error
rmse = np.sqrt(np.mean((df['human_grade'] - df['ai_grade']) ** 2))

# Additional: Agreement within ±1 mark
within_1_mark = np.mean(np.abs(df['human_grade'] - df['ai_grade']) <= 1.0) * 100

print("=" * 50)
print("  AuraGrade AI — Research Metrics Report")
print("=" * 50)
print(f"  Samples Evaluated     : {len(df)}")
print(f"  Pearson Correlation (r): {corr:.4f}  (p={p_value:.4e})")
print(f"  Mean Absolute Error   : {mae:.4f}")
print(f"  Root Mean Square Error: {rmse:.4f}")
print(f"  Quadratic Weighted κ  : {qwk:.4f}")
print(f"  Agreement within ±1   : {within_1_mark:.1f}%")
print(f"  Avg AI Confidence     : {df['confidence'].mean():.2f}")
print("=" * 50)

# Quality thresholds
print("\n  Quality Assessment:")
print(f"  {'✅' if corr > 0.85 else '⚠️'} Correlation: {'Excellent' if corr > 0.85 else 'Needs improvement'} (target: r > 0.85)")
print(f"  {'✅' if mae < 1.0 else '⚠️'} MAE: {'Excellent' if mae < 1.0 else 'Needs improvement'} (target: < 1.0)")
print(f"  {'✅' if qwk > 0.80 else '⚠️'} QWK: {'Excellent' if qwk > 0.80 else 'Needs improvement'} (target: κ > 0.80)")
print()

# ─── 2. Visualization: Correlation Plot ──────────────────────
sns.set_theme(style="darkgrid")
fig, axes = plt.subplots(1, 3, figsize=(20, 6))

# Plot 1: AI vs Human Regression
ax1 = axes[0]
sns.regplot(
    x='human_grade', y='ai_grade', data=df,
    color='#3b82f6', marker='+', scatter_kws={'s': 100, 'linewidths': 2},
    ax=ax1
)
# Perfect agreement line
ax1.plot([0, 10], [0, 10], '--', color='gray', alpha=0.5, label='Perfect Agreement')
ax1.set_title(f"AI vs. Human Grading Consistency\n(r = {corr:.2f}, p = {p_value:.2e})", fontsize=12, fontweight='bold')
ax1.set_xlabel("Professor's Marks", fontsize=11)
ax1.set_ylabel("AuraGrade AI Marks", fontsize=11)
ax1.set_xlim(0, 10.5)
ax1.set_ylim(0, 10.5)
ax1.legend()

# Plot 2: Bland-Altman Plot (Agreement Analysis)
ax2 = axes[1]
mean_grades = (df['human_grade'] + df['ai_grade']) / 2
diff_grades = df['human_grade'] - df['ai_grade']
mean_diff = diff_grades.mean()
std_diff = diff_grades.std()

ax2.scatter(mean_grades, diff_grades, c='#10b981', s=80, edgecolors='white', zorder=5)
ax2.axhline(y=mean_diff, color='#3b82f6', linestyle='-', label=f'Mean Diff: {mean_diff:.2f}')
ax2.axhline(y=mean_diff + 1.96 * std_diff, color='#ef4444', linestyle='--', label=f'+1.96 SD: {mean_diff + 1.96 * std_diff:.2f}')
ax2.axhline(y=mean_diff - 1.96 * std_diff, color='#ef4444', linestyle='--', label=f'-1.96 SD: {mean_diff - 1.96 * std_diff:.2f}')
ax2.set_title("Bland-Altman Agreement Plot", fontsize=12, fontweight='bold')
ax2.set_xlabel("Mean of Human & AI Grade", fontsize=11)
ax2.set_ylabel("Difference (Human - AI)", fontsize=11)
ax2.legend(fontsize=9)

# Plot 3: Error Distribution
ax3 = axes[2]
errors = df['human_grade'] - df['ai_grade']
ax3.hist(errors, bins=8, color='#8b5cf6', edgecolor='white', alpha=0.8)
ax3.axvline(x=0, color='#ef4444', linestyle='--', linewidth=2, label='Zero Error')
ax3.axvline(x=errors.mean(), color='#3b82f6', linestyle='-', linewidth=2, label=f'Mean: {errors.mean():.2f}')
ax3.set_title("Error Distribution (Human - AI)", fontsize=12, fontweight='bold')
ax3.set_xlabel("Grade Difference", fontsize=11)
ax3.set_ylabel("Frequency", fontsize=11)
ax3.legend()

plt.tight_layout()
plt.savefig('research_metrics_plots.png', dpi=300, bbox_inches='tight')
print("📊 Saved: research_metrics_plots.png")

# ─── 3. Confusion Heatmap (Rounded Grades) ───────────────────
fig2, ax4 = plt.subplots(figsize=(8, 6))
human_rounded = np.rint(df['human_grade']).astype(int)
ai_rounded = np.rint(df['ai_grade']).astype(int)

# Create confusion matrix
all_grades = range(0, 11)
confusion = pd.crosstab(
    pd.Categorical(human_rounded, categories=all_grades),
    pd.Categorical(ai_rounded, categories=all_grades),
    dropna=False
)

sns.heatmap(
    confusion, annot=True, fmt='d', cmap='Blues',
    xticklabels=all_grades, yticklabels=all_grades,
    ax=ax4, cbar_kws={'label': 'Count'}
)
ax4.set_title(f"Grade Agreement Heatmap (QWK = {qwk:.2f})", fontsize=12, fontweight='bold')
ax4.set_xlabel("AI Grade (Rounded)", fontsize=11)
ax4.set_ylabel("Human Grade (Rounded)", fontsize=11)

plt.tight_layout()
plt.savefig('confusion_heatmap.png', dpi=300, bbox_inches='tight')
print("📊 Saved: confusion_heatmap.png")

# ─── 4. Confidence vs Error Analysis ─────────────────────────
fig3, ax5 = plt.subplots(figsize=(8, 6))
abs_errors = np.abs(df['human_grade'] - df['ai_grade'])
scatter = ax5.scatter(
    df['confidence'], abs_errors,
    c=abs_errors, cmap='RdYlGn_r', s=100, edgecolors='white', zorder=5
)
plt.colorbar(scatter, label='Absolute Error')

# Trend line
z = np.polyfit(df['confidence'], abs_errors, 1)
p = np.poly1d(z)
conf_range = np.linspace(df['confidence'].min(), df['confidence'].max(), 100)
ax5.plot(conf_range, p(conf_range), '--', color='#3b82f6', alpha=0.7, label='Trend')

ax5.set_title("AI Confidence vs. Grading Error", fontsize=12, fontweight='bold')
ax5.set_xlabel("AI Confidence Score", fontsize=11)
ax5.set_ylabel("Absolute Error |Human - AI|", fontsize=11)
ax5.legend()

plt.tight_layout()
plt.savefig('confidence_vs_error.png', dpi=300, bbox_inches='tight')
print("📊 Saved: confidence_vs_error.png")

print("\n✅ All research artifacts generated successfully.")
