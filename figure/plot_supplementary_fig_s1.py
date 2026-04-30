import matplotlib.pyplot as plt
import numpy as np

# 确保 PDF 导出时将文本作为路径/字体处理，而不是位图
plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

# 1. 完整数据配置
data = [
    # Tier 1: Resource Awareness
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R1', 'User Input Retrieval'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R2', 'Session Context Retrieval'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R3', 'Long-term Memory Access'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R4', 'Attachment Processing'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R5', 'Repository File Access'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R6', 'Arbitrary FS Access'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R7', 'Knowledge Base Access'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R8', 'Connector Data Retrieval'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R9', 'Resource Enumeration'),
    ('T1', 'Resource Awareness', 'R', 'Read & Retrieval', 'R10', 'Cross-source Merging'),
    ('T1', 'Resource Awareness', 'Q', 'Discovery & Query', 'Q1', 'Read-only Discovery'),
    ('T1', 'Resource Awareness', 'Q', 'Discovery & Query', 'Q2', 'Structured Aggregation'),
    ('T1', 'Resource Awareness', 'Q', 'Discovery & Query', 'Q3', 'Sensitive Record Retrieval'),
    ('T1', 'Resource Awareness', 'Q', 'Discovery & Query', 'Q4', 'Heuristic Recommendation'),
    ('T1', 'Resource Awareness', 'S', 'System Sensing', 'S1', 'Camera Capture'),
    ('T1', 'Resource Awareness', 'S', 'System Sensing', 'S2', 'Audio Recording'),
    ('T1', 'Resource Awareness', 'S', 'System Sensing', 'S3', 'Biometric Access'),
    ('T1', 'Resource Awareness', 'S', 'System Sensing', 'S4', 'Precise Geolocation'),
    ('T1', 'Resource Awareness', 'S', 'System Sensing', 'S5', 'Persistent Tracking'),
    ('T1', 'Resource Awareness', 'S', 'System Sensing', 'S6', 'Proximity Scanning'),
    ('T1', 'Resource Awareness', 'S', 'System Sensing', 'S7', 'System Telemetry'),

    # Tier 2: Interaction & Comm
    ('T2', 'Interaction & Comm', 'W', 'External Connectivity', 'W1', 'Public Web Browsing'),
    ('T2', 'Interaction & Comm', 'W', 'External Connectivity', 'W2', 'External API Invocation'),
    ('T2', 'Interaction & Comm', 'W', 'External Connectivity', 'W3', 'Remote Resource Downloading'),
    ('T2', 'Interaction & Comm', 'W', 'External Connectivity', 'W4', 'Discovery-driven Orchestration'),
    ('T2', 'Interaction & Comm', 'U', 'User Emulation', 'U1', 'Visual Input Capture'),
    ('T2', 'Interaction & Comm', 'U', 'User Emulation', 'U2', 'UI Event Emulation'),
    ('T2', 'Interaction & Comm', 'U', 'User Emulation', 'U3', 'Clipboard Management'),
    ('T2', 'Interaction & Comm', 'U', 'User Emulation', 'U4', 'Input Event Interception'),
    ('T2', 'Interaction & Comm', 'C', 'Real-time Comm', 'C1', 'Peripheral Control'),
    ('T2', 'Interaction & Comm', 'C', 'Real-time Comm', 'C2', 'Push Messaging'),
    ('T2', 'Interaction & Comm', 'C', 'Real-time Comm', 'C3', 'Impersonated Messaging'),
    ('T2', 'Interaction & Comm', 'C', 'Real-time Comm', 'C4', 'Persistent Data Streaming'),
    ('T2', 'Interaction & Comm', 'C', 'Real-time Comm', 'C5', 'Persistent Remote Connection'),

    # Tier 3: Environment Control
    ('T3', 'Environment Control', 'X', 'Code & Execution', 'X1', 'Shell Command Execution'),
    ('T3', 'Environment Control', 'X', 'Code & Execution', 'X2', 'Scripting Runtime Execution'),
    ('T3', 'Environment Control', 'X', 'Code & Execution', 'X3', 'Containerized Task Execution'),
    ('T3', 'Environment Control', 'X', 'Code & Execution', 'X4', 'Dependency Management'),
    ('T3', 'Environment Control', 'X', 'Code & Execution', 'X5', 'Network-enabled Execution'),
    ('T3', 'Environment Control', 'X', 'Code & Execution', 'X6', 'Local FS Mutation'),
    ('T3', 'Environment Control', 'X', 'Code & Execution', 'X7', 'Secret & Env Access'),
    ('T3', 'Environment Control', 'X', 'Code & Execution', 'X8', 'Local Utility Invocation'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'G1', 'Advisory Text Gen'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'G2', 'Schema-based Drafting'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'G3', 'Transient Persistence'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'G4', 'Project Workspace Mod'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'G5', 'Mass File Mutation'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'O1', 'Remote Draft Creation'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'O2', 'Remote Resource Mutation'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'O3', 'Bulk Remote Operation'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'O4', 'Irreversible Deletion'),
    ('T3', 'Environment Control', 'G/O', 'Gen & Mutation', 'O5', 'Automated Publishing'),
    ('T3', 'Environment Control', 'K', 'Kernel & Sys Mgmt', 'K1', 'Sys Config Mutation'),
    ('T3', 'Environment Control', 'K', 'Kernel & Sys Mgmt', 'K2', 'Hardware State Control'),
    ('T3', 'Environment Control', 'K', 'Kernel & Sys Mgmt', 'K3', 'App Life-cycle Mgmt'),
    ('T3', 'Environment Control', 'K', 'Kernel & Sys Mgmt', 'K4', 'Task Sched & Wake Locks'),
    ('T3', 'Environment Control', 'K', 'Kernel & Sys Mgmt', 'K5', 'Process Life-cycle Mgmt'),
    ('T3', 'Environment Control', 'K', 'Kernel & Sys Mgmt', 'K6', 'Global Environment Styling'),

    # Tier 4: Agency & Orchestration
    ('T4', 'Agency & Orchestration', 'A', 'Automation & Triggers', 'A1', 'Explicit User Invocation'),
    ('T4', 'Agency & Orchestration', 'A', 'Automation & Triggers', 'A2', 'Manual Gatekeeping'),
    ('T4', 'Agency & Orchestration', 'A', 'Automation & Triggers', 'A3', 'Scheduled Execution'),
    ('T4', 'Agency & Orchestration', 'A', 'Automation & Triggers', 'A4', 'Event-driven Automation'),
    ('T4', 'Agency & Orchestration', 'A', 'Automation & Triggers', 'A5', 'Continuous Observability'),
    ('T4', 'Agency & Orchestration', 'A', 'Automation & Triggers', 'A6', 'Condition-based Automation'),
    ('T4', 'Agency & Orchestration', 'A', 'Automation & Triggers', 'A7', 'Iterative Task Automation'),
    ('T4', 'Agency & Orchestration', 'I', 'Identity Agency', 'I1', 'Single-domain Proxy'),
    ('T4', 'Agency & Orchestration', 'I', 'Identity Agency', 'I2', 'Cross-domain Delegation'),
    ('T4', 'Agency & Orchestration', 'I', 'Identity Agency', 'I3', 'Inter-system Data Movement'),
    ('T4', 'Agency & Orchestration', 'I', 'Identity Agency', 'I4', 'Credential Passthrough'),
    ('T4', 'Agency & Orchestration', 'I', 'Identity Agency', 'I5', 'Implicit Privilege Inheritance'),
    ('T4', 'Agency & Orchestration', 'I', 'Identity Agency', 'I6', 'Root Credential Mgmt'),
    ('T4', 'Agency & Orchestration', 'I', 'Identity Agency', 'I7', 'Cross-device Synchronization'),
]

# 2. 颜色方案
colors_tier = {'T1': '#3498DB', 'T2': '#E67E22', 'T3': '#E74C3C', 'T4': '#9B59B6'}
colors_cat = {
    'R': '#5DADE2', 'Q': '#85C1E9', 'S': '#AED6F1',
    'W': '#EB984E', 'U': '#F0B27A', 'C': '#F5CBA7',
    'X': '#EC7063', 'G/O': '#F1948A', 'K': '#FADBD8',
    'A': '#AF7AC5', 'I': '#C39BD3'
}

# 3. 数据处理
tier_counts = {}
cat_counts = {}
cat_full_names_map = {}
atom_labels = []
atom_colors = []
tiers_order = ['T1', 'T2', 'T3', 'T4']
unique_cats_ordered = []

for t_id, t_name, c_id, c_name, a_id, a_name in data:
    tier_counts[t_id] = tier_counts.get(t_id, 0) + 1
    ckey = f"{t_id}_{c_id}"
    if ckey not in unique_cats_ordered:
        unique_cats_ordered.append(ckey)
    cat_counts[ckey] = cat_counts.get(ckey, 0) + 1
    cat_full_names_map[ckey] = (c_id, c_name)
    atom_labels.append(f"{a_id}: {a_name}")
    atom_colors.append(colors_cat[c_id])

# 4. 绘图执行
fig, ax = plt.subplots(figsize=(28, 28), dpi=300)
size = 0.35

# --- 内环: Tiers ---
tier_vals = [tier_counts[t] for t in tiers_order]
tier_colors_list = [colors_tier[t] for t in tiers_order]
tier_labels_display = [f"{t}\n{data[next(i for i, v in enumerate(data) if v[0] == t)][1]}" for t in tiers_order]

patches_t, _ = ax.pie(tier_vals, radius=1.3 - 2 * size, colors=tier_colors_list,
                      wedgeprops=dict(width=size, edgecolor='w', linewidth=3))

for i, p in enumerate(patches_t):
    ang = (p.theta2 + p.theta1) / 2.
    y = np.sin(np.deg2rad(ang)) * 0.45
    x = np.cos(np.deg2rad(ang)) * 0.45
    ax.text(x, y, tier_labels_display[i], ha='center', va='center', fontsize=22, weight='bold', color='white')

# --- 中环: Categories (ID: Full Name 格式) ---
cat_vals = [cat_counts[k] for k in unique_cats_ordered]
cat_colors_list = [colors_cat[k.split('_')[1]] for k in unique_cats_ordered]
cat_labels_display = [f"{cat_full_names_map[k][0]}: {cat_full_names_map[k][1]}" for k in unique_cats_ordered]

patches_c, _ = ax.pie(cat_vals, radius=1.3 - size, colors=cat_colors_list,
                      wedgeprops=dict(width=size, edgecolor='w', linewidth=2.5))

for i, p in enumerate(patches_c):
    ang = (p.theta2 + p.theta1) / 2.
    y = np.sin(np.deg2rad(ang)) * 0.78
    x = np.cos(np.deg2rad(ang)) * 0.78
    display_name = cat_labels_display[i].replace(' & ', ' &\n').replace('And ', 'And\n')
    ax.text(x, y, display_name, ha='center', va='center', fontsize=18, weight='bold')

# --- 外环: Atoms ---
patches_a, _ = ax.pie([1] * 72, radius=1.3, colors=atom_colors,
                      wedgeprops=dict(width=size, edgecolor='w', linewidth=0.8))

for i, p in enumerate(patches_a):
    ang = (p.theta2 + p.theta1) / 2.
    r_text = 1.3 - size / 2
    y = np.sin(np.deg2rad(ang)) * r_text
    x = np.cos(np.deg2rad(ang)) * r_text

    rotation = ang
    if 90 < ang < 270:
        rotation -= 180

    ax.text(x, y, atom_labels[i], rotation=rotation, ha='center', va='center',
            fontsize=11, weight='semibold', rotation_mode='anchor')

# --- 中心圆 ---
center_circle = plt.Circle((0, 0), 1.3 - 3 * size, color='white', fc='white', zorder=10)
ax.add_artist(center_circle)
ax.text(0, 0, 'PermAudit', ha='center', va='center', fontsize=46, weight='bold', zorder=11)

# plt.title("Supplementary Figure S1: Skill Permission Taxonomy Panorama", fontsize=36, pad=80)
plt.tight_layout()

# 保存 PDF 矢量图
# transparent=True 可以让背景透明，方便放入 PPT 或排版软件
plt.savefig("PermAudit_Framework.pdf",
            format='pdf',
            transparent=True,
            bbox_inches='tight',
            pad_inches=0.1)
