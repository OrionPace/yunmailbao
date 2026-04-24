import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const colors = {
  base: '#070a12',
  surface: '#0d1220',
  overlay: 'rgba(10, 16, 30, 0.76)',
  border: 'rgba(74, 222, 255, 0.28)',
  text: '#e8f7ff',
  secondary: '#a8bfd1',
  muted: '#6f8499',
  cyan: '#20f7d2',
  magenta: '#ff3df2',
  amber: '#ffb020',
  danger: '#ff4f7b',
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

const fade = (frame: number, from: number, duration: number) =>
  interpolate(frame, [from, from + duration], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const rise = (frame: number, from: number, distance = 30) =>
  interpolate(frame, [from, from + 24], [distance, 0], {
    ...clamp,
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

type Focus =
  | 'overview'
  | 'accounts'
  | 'excel'
  | 'editor'
  | 'engine'
  | 'test'
  | 'logs'
  | 'doc';

type SceneProps = {
  eyebrow: string;
  title: string;
  body: string;
  focus: Focus;
  progress?: number;
};

const scenes: SceneProps[] = [
  {
    eyebrow: 'STEP 01',
    title: '真实界面：主控制台',
    body: '先确认左侧配置区、右侧监控区和顶部文档入口。新版系统说明页也已经改成云邮宝操作手册。',
    focus: 'overview',
  },
  {
    eyebrow: 'STEP 02',
    title: '填写发件账号池',
    body: '输入发件人别名、邮箱和 SMTP 授权码。授权码会在视频中脱敏，真实值只保存在本机 .env 或运行界面。',
    focus: 'accounts',
  },
  {
    eyebrow: 'STEP 03',
    title: '导入测试名单',
    body: '使用 tests/create_sample_recipients.py 生成样例 Excel，上传后选择姓名列和邮箱列，避免列映射错误。',
    focus: 'excel',
  },
  {
    eyebrow: 'STEP 04',
    title: '正文从空白开始',
    body: '富文本编辑器不再带机构示例。写入主题、正文、<人名> 占位符，并按需添加 PDF 附件。',
    focus: 'editor',
  },
  {
    eyebrow: 'STEP 05',
    title: '设置保守发送节奏',
    body: '测试阶段单批次并发保持 1，抖动 5-15 秒。确认成功后再逐步提高发送速度。',
    focus: 'engine',
  },
  {
    eyebrow: 'STEP 06',
    title: '测试邮箱发送过程',
    body: '手动测试脚本读取 .env，使用脱敏发件账号向测试收件箱发送。画面展示流程，不暴露授权码。',
    focus: 'test',
    progress: 0.55,
  },
  {
    eyebrow: 'STEP 07',
    title: '看日志，导出失败记录',
    body: '右侧实时控制台会显示上传、列识别、发送成功和失败分类。失败记录可导出为 Excel 继续排查。',
    focus: 'logs',
    progress: 0.82,
  },
  {
    eyebrow: 'STEP 08',
    title: '上线与打包路径',
    body: '部署到阿里云前先补鉴权、上传限制和 CORS 白名单。桌面版最终仍用 build.bat 输出 EXE。',
    focus: 'doc',
  },
];

const Background = () => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 1440], [0, 280], clamp);

  return (
    <AbsoluteFill
      style={{
        background:
          'linear-gradient(135deg, #060812 0%, #10172b 46%, #120719 100%)',
        color: colors.text,
        fontFamily:
          'Inter, "Microsoft YaHei", "PingFang SC", Arial, sans-serif',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(rgba(32, 247, 210, 0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 61, 242, 0.04) 1px, transparent 1px)
          `,
          backgroundSize: '42px 42px',
          transform: `translate(${drift % 42}px, ${drift % 42}px)`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 980,
          height: 980,
          left: -340,
          top: 80,
          background:
            'radial-gradient(circle, rgba(32,247,210,.22), transparent 64%)',
          filter: 'blur(26px)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 900,
          height: 900,
          right: -260,
          bottom: -200,
          background:
            'radial-gradient(circle, rgba(255,61,242,.20), transparent 66%)',
          filter: 'blur(28px)',
        }}
      />
    </AbsoluteFill>
  );
};

const Panel = ({
  children,
  style,
  active,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
  active?: boolean;
}) => (
  <div
    style={{
      background: active
        ? 'linear-gradient(145deg, rgba(32,247,210,.10), rgba(255,61,242,.05)), rgba(8,13,24,.86)'
        : colors.overlay,
      border: `1px solid ${active ? colors.cyan : colors.border}`,
      borderRadius: 16,
      boxShadow: active
        ? '0 0 30px rgba(32,247,210,.18), inset 0 0 18px rgba(32,247,210,.05)'
        : '0 18px 60px rgba(0,0,0,.26)',
      ...style,
    }}
  >
    {children}
  </div>
);

const Field = ({
  label,
  value,
  active,
  width,
}: {
  label?: string;
  value: string;
  active?: boolean;
  width?: number | string;
}) => (
  <div style={{width: width ?? '100%'}}>
    {label ? (
      <div style={{fontSize: 14, color: colors.secondary, marginBottom: 6}}>
        {label}
      </div>
    ) : null}
    <div
      style={{
        padding: '13px 15px',
        borderRadius: 10,
        background: 'rgba(7,10,18,.74)',
        border: `1px solid ${active ? colors.cyan : colors.border}`,
        color: active ? colors.text : colors.secondary,
        fontSize: 17,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}
    >
      {value}
    </div>
  </div>
);

const Header = ({activeDoc}: {activeDoc?: boolean}) => (
  <Panel
    style={{
      height: 76,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 26px',
      marginBottom: 22,
    }}
  >
    <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          border: `2px solid ${colors.cyan}`,
          display: 'grid',
          placeItems: 'center',
          color: colors.cyan,
          fontWeight: 900,
        }}
      >
        ✉
      </div>
      <div style={{fontSize: 24, fontWeight: 900}}>云邮宝</div>
    </div>
    <div style={{display: 'flex', alignItems: 'center', gap: 16}}>
      <div
        style={{
          display: 'flex',
          gap: 6,
          padding: 4,
          borderRadius: 14,
          border: `1px solid ${colors.border}`,
          background: colors.surface,
        }}
      >
        <Tab active={!activeDoc}>主控制台</Tab>
        <Tab active={activeDoc}>系统说明(DOC)</Tab>
      </div>
      <div style={{color: colors.secondary, fontSize: 17}}>● 系统就绪</div>
    </div>
  </Panel>
);

const Tab = ({active, children}: {active?: boolean; children: React.ReactNode}) => (
  <div
    style={{
      padding: '10px 18px',
      borderRadius: 10,
      color: active ? colors.cyan : colors.secondary,
      background: active ? 'rgba(32,247,210,.08)' : 'transparent',
      boxShadow: active ? 'inset 0 0 0 1px rgba(32,247,210,.18)' : 'none',
      fontSize: 16,
      fontWeight: 800,
    }}
  >
    {children}
  </div>
);

const AppScreen = ({focus, progress = 0}: {focus: Focus; progress?: number}) => {
  const is = (target: Focus) => focus === target;
  const showRuntime = focus === 'test' || focus === 'logs';
  const activeDoc = focus === 'doc';

  return (
    <div
      style={{
        position: 'absolute',
        right: 70,
        top: 68,
        width: 1240,
        height: 860,
      }}
    >
      <Header activeDoc={activeDoc} />
      {activeDoc ? <DocPage /> : null}
      {!activeDoc ? (
        <div style={{display: 'grid', gridTemplateColumns: '1fr 365px', gap: 22}}>
          <Panel style={{height: 760, padding: 30}} active={focus === 'overview'}>
            <div style={{display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20}}>
              <div style={{width: 4, height: 22, borderRadius: 6, background: colors.cyan}} />
              <h2 style={{fontSize: 28, margin: 0}}>智能配置</h2>
            </div>
            <div style={{display: 'grid', gap: 18}}>
              <FormBlock title="发件人账号池配置" active={is('accounts')}>
                <div style={{display: 'flex', gap: 10}}>
                  <Field value="培训组" width={118} active={is('accounts')} />
                  <Field value="2085****23@qq.com" active={is('accounts')} />
                  <Field value="授权码 ************" active={is('accounts')} />
                </div>
                <SmallButton>+ 继续添加账号</SmallButton>
              </FormBlock>

              <FormBlock title="收件人" active={is('excel') || is('test')}>
                <div
                  style={{
                    padding: 18,
                    borderRadius: 14,
                    border: `2px dashed ${is('excel') || is('test') ? colors.cyan : colors.border}`,
                    textAlign: 'center',
                    color: colors.secondary,
                    fontSize: 18,
                    background: 'rgba(7,10,18,.5)',
                  }}
                >
                  {is('excel') || is('test') ? 'sample_recipients.xlsx' : '点击选择或拖拽 Excel 文件'}
                </div>
                {(is('excel') || is('test') || showRuntime) && (
                  <div style={{display: 'flex', gap: 12, marginTop: 12}}>
                    <Field label="姓名列" value="姓名" active width="50%" />
                    <Field label="邮箱列" value="邮箱" active width="50%" />
                  </div>
                )}
              </FormBlock>

              <div style={{display: 'grid', gridTemplateColumns: '1fr 230px', gap: 14}}>
                <FormBlock title="主题" active={is('editor')}>
                  <Field value={is('editor') ? '【测试】云邮宝发送链路验证' : '请输入邮件主题'} active={is('editor')} />
                </FormBlock>
                <FormBlock title="附件" active={is('editor')}>
                  <Field value={is('editor') ? 'intro.pdf' : '选择 PDF'} active={is('editor')} />
                </FormBlock>
              </div>

              <FormBlock title="富文本正文编写  占位符: <人名>" active={is('editor')}>
                <Editor active={is('editor')} />
              </FormBlock>

              <FormBlock title="发件引擎与防封策略" active={is('engine')}>
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10}}>
                  <Field label="窗口开始" value="08:00" active={is('engine')} />
                  <Field label="窗口结束" value="21:40" active={is('engine')} />
                  <Field label="并发" value="1" active={is('engine')} />
                  <Field label="最小抖动" value="5" active={is('engine')} />
                  <Field label="最大抖动" value="15" active={is('engine')} />
                </div>
              </FormBlock>
            </div>
          </Panel>

          <Dashboard focus={focus} progress={progress} />
        </div>
      ) : null}
    </div>
  );
};

const FormBlock = ({
  title,
  active,
  children,
}: {
  title: string;
  active?: boolean;
  children: React.ReactNode;
}) => (
  <div
    style={{
      padding: 16,
      borderRadius: 14,
      border: `1px solid ${active ? colors.cyan : 'rgba(74,222,255,.14)'}`,
      background: active ? 'rgba(32,247,210,.07)' : 'rgba(255,255,255,.025)',
      boxShadow: active ? '0 0 24px rgba(32,247,210,.15)' : 'none',
    }}
  >
    <div style={{fontSize: 16, color: active ? colors.cyan : colors.secondary, marginBottom: 10, fontWeight: 900}}>
      {title}
    </div>
    {children}
  </div>
);

const SmallButton = ({children}: {children: React.ReactNode}) => (
  <div
    style={{
      display: 'inline-flex',
      marginTop: 10,
      padding: '8px 12px',
      borderRadius: 8,
      border: `1px solid ${colors.border}`,
      color: colors.text,
      background: colors.surface,
      fontSize: 15,
      fontWeight: 800,
    }}
  >
    {children}
  </div>
);

const Editor = ({active}: {active?: boolean}) => (
  <div
    style={{
      height: 130,
      borderRadius: 12,
      overflow: 'hidden',
      border: `1px solid ${active ? colors.cyan : colors.border}`,
      background: colors.base,
    }}
  >
    <div
      style={{
        height: 34,
        borderBottom: `1px solid ${colors.border}`,
        display: 'flex',
        gap: 8,
        alignItems: 'center',
        padding: '0 12px',
        color: colors.muted,
        fontSize: 13,
      }}
    >
      <span>B</span>
      <span>I</span>
      <span>U</span>
      <span>字号</span>
      <span>颜色</span>
      <span>图片</span>
    </div>
    <div style={{padding: 16, fontSize: 18, lineHeight: 1.55, color: active ? colors.text : colors.muted}}>
      {active ? (
        <>
          <div>尊敬的 &lt;人名&gt;：</div>
          <div>您好，这是一封云邮宝链路测试邮件。</div>
        </>
      ) : (
        <div>编辑器默认空白，避免误发示例内容。</div>
      )}
    </div>
  </div>
);

const Dashboard = ({focus, progress}: {focus: Focus; progress: number}) => {
  const running = focus === 'test' || focus === 'logs';
  const done = focus === 'logs';
  const percent = done ? 86 : running ? Math.round(progress * 100) : 0;

  return (
    <div style={{display: 'grid', gap: 18}}>
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12}}>
        <Metric label="总计划" value={running || done ? '3' : '0'} />
        <Metric label="已送达" value={done ? '2' : running ? '1' : '0'} accent={colors.cyan} />
        <Metric label="失败" value={done ? '1' : '0'} accent={colors.danger} />
      </div>
      <Panel style={{padding: 20}} active={running}>
        <div style={{display: 'flex', justifyContent: 'space-between', color: colors.secondary, fontSize: 17}}>
          <span>队列完成进度</span>
          <span>{percent}%</span>
        </div>
        <div style={{height: 10, marginTop: 14, borderRadius: 99, background: 'rgba(255,255,255,.12)', overflow: 'hidden'}}>
          <div
            style={{
              height: '100%',
              width: `${percent}%`,
              background: `linear-gradient(90deg, ${colors.magenta}, ${colors.cyan})`,
              boxShadow: `0 0 18px ${colors.cyan}`,
            }}
          />
        </div>
      </Panel>
      <Panel style={{height: 570, overflow: 'hidden'}} active={focus === 'logs' || focus === 'test'}>
        <div
          style={{
            height: 52,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 18px',
            borderBottom: `1px solid ${colors.border}`,
          }}
        >
          <strong style={{color: colors.secondary}}>实时控制台记录</strong>
          {done && (
            <span style={{color: colors.text, background: `linear-gradient(135deg, ${colors.magenta}, ${colors.cyan})`, padding: '7px 12px', borderRadius: 8}}>
              导出失败记录 (1)
            </span>
          )}
        </div>
        <div style={{padding: 18, fontFamily: 'Consolas, monospace', fontSize: 17, lineHeight: 1.85}}>
          <Log muted>Awaiting system initialization...</Log>
          {(running || done) && (
            <>
              <Log ok>[✓] 成功上传载入: sample_recipients.xlsx</Log>
              <Log ok>[✓] 检测到 2 列: 姓名, 邮箱</Log>
              <Log>[队列] 使用账号: 2085****23@qq.com</Log>
              <Log>[队列] 正在发送至 zhangsan@example.com</Log>
              <Log ok>[✓] 发送成功 - Success</Log>
            </>
          )}
          {done && (
            <>
              <Log>[队列] 正在发送至 lisi@example.com</Log>
              <Log fail>[!] 发送失败 [地址不存在/被退回]</Log>
              <Log ok>[✓] 已生成失败记录，可导出复核</Log>
            </>
          )}
        </div>
      </Panel>
    </div>
  );
};

const Metric = ({label, value, accent = colors.text}: {label: string; value: string; accent?: string}) => (
  <Panel style={{padding: 18, textAlign: 'center'}}>
    <div style={{fontSize: 14, color: colors.secondary, marginBottom: 8}}>{label}</div>
    <div style={{fontSize: 38, fontWeight: 900, color: accent}}>{value}</div>
  </Panel>
);

const Log = ({
  children,
  ok,
  fail,
  muted,
}: {
  children: React.ReactNode;
  ok?: boolean;
  fail?: boolean;
  muted?: boolean;
}) => (
  <div style={{color: ok ? colors.cyan : fail ? colors.danger : muted ? colors.muted : colors.text}}>
    {children}
  </div>
);

const DocPage = () => (
  <Panel style={{height: 760, padding: 34}}>
    <div style={{display: 'grid', gridTemplateColumns: '1fr 250px', gap: 24, marginBottom: 26}}>
      <div>
        <div style={{color: colors.cyan, fontSize: 17, fontWeight: 900, letterSpacing: 3}}>YUNYOUBAO DOC</div>
        <h2 style={{fontSize: 44, margin: '12px 0 8px'}}>云邮宝操作手册</h2>
        <p style={{fontSize: 21, color: colors.secondary, margin: 0}}>
          账号配置、名单导入、正文编写、发送监控和上线注意事项。
        </p>
      </div>
      <Panel style={{padding: 20}}>
        <div style={{color: colors.secondary}}>运行模式</div>
        <strong style={{display: 'block', fontSize: 32, color: colors.cyan, margin: '8px 0'}}>本地优先</strong>
        <div style={{color: colors.muted}}>账号与日志默认保存在当前机器</div>
      </Panel>
    </div>
    <div style={{display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16}}>
      {[
        ['1. 准备发件账号', '别名、邮箱、SMTP 授权码，真实授权码不入库。'],
        ['2. 导入收件人 Excel', '上传后确认姓名列和邮箱列映射。'],
        ['3. 编写正文与附件', '编辑器默认空白，支持 <人名> 占位符。'],
        ['4. 设置发送节奏', '窗口、并发和抖动从保守参数开始。'],
        ['5. 监控与失败导出', '实时日志、失败分类、Excel 导出。'],
        ['上线前注意', '补鉴权、上传限制、CORS 白名单和审计。'],
      ].map(([title, body], index) => (
        <Panel key={title} style={{padding: 20}} active={index === 5}>
          <h3 style={{fontSize: 23, margin: '0 0 10px'}}>{title}</h3>
          <p style={{fontSize: 18, lineHeight: 1.5, color: colors.secondary, margin: 0}}>{body}</p>
        </Panel>
      ))}
    </div>
  </Panel>
);

const TestWorkflow = () => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        position: 'absolute',
        left: 96,
        bottom: 70,
        width: 690,
        opacity: fade(frame, 12, 18),
        transform: `translateY(${rise(frame, 12, 24)}px)`,
      }}
    >
      <Panel style={{padding: 24}} active>
        <div style={{color: colors.amber, fontSize: 18, fontWeight: 900, letterSpacing: 2, marginBottom: 12}}>
          TEST EMAIL WORKFLOW
        </div>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14}}>
          <TestCard title="测试脚本" lines={['tests/manual_email_smoke.py', '读取 .env 中 ACCOUNT_1_*']} />
          <TestCard title="测试名单" lines={['sample_recipients.xlsx', 'zhangsan@example.com', 'lisi@example.com']} />
          <TestCard title="安全展示" lines={['发件: 2085****23@qq.com', '授权码: ************']} />
          <TestCard title="结果确认" lines={['控制台成功日志', '失败记录可导出']} />
        </div>
      </Panel>
    </div>
  );
};

const TestCard = ({title, lines}: {title: string; lines: string[]}) => (
  <div style={{border: `1px solid ${colors.border}`, borderRadius: 12, padding: 14, background: 'rgba(255,255,255,.035)'}}>
    <div style={{fontSize: 16, color: colors.cyan, fontWeight: 900, marginBottom: 8}}>{title}</div>
    {lines.map((line) => (
      <div key={line} style={{fontSize: 16, color: colors.secondary, lineHeight: 1.55}}>
        {line}
      </div>
    ))}
  </div>
);

const SceneText = ({scene}: {scene: SceneProps}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: 'absolute', left: 84, top: 120, width: 650}}>
      <div
        style={{
          color: colors.cyan,
          fontSize: 22,
          fontWeight: 900,
          letterSpacing: 3,
          opacity: fade(frame, 0, 16),
        }}
      >
        {scene.eyebrow}
      </div>
      <h1
        style={{
          margin: '22px 0 20px',
          fontSize: 64,
          lineHeight: 1.05,
          opacity: fade(frame, 6, 18),
          transform: `translateY(${rise(frame, 6, 30)}px)`,
        }}
      >
        {scene.title}
      </h1>
      <p
        style={{
          fontSize: 29,
          lineHeight: 1.45,
          color: colors.secondary,
          opacity: fade(frame, 18, 18),
          transform: `translateY(${rise(frame, 18, 22)}px)`,
        }}
      >
        {scene.body}
      </p>
    </div>
  );
};

const Intro = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Background />
      <div style={{position: 'absolute', left: 100, top: 180, width: 820}}>
        <div style={{color: colors.cyan, fontSize: 25, fontWeight: 900, letterSpacing: 4, opacity: fade(frame, 0, 20)}}>
          YUNYOUBAO OPERATION VIDEO
        </div>
        <h1
          style={{
            fontSize: 102,
            lineHeight: 0.96,
            margin: '24px 0',
            opacity: fade(frame, 8, 24),
            transform: `translateY(${rise(frame, 8, 38)}px)`,
          }}
        >
          云邮宝<br />完整操作教程
        </h1>
        <p style={{fontSize: 34, color: colors.secondary, lineHeight: 1.4, opacity: fade(frame, 28, 18)}}>
          节奏放慢，界面贴近当前 App，并加入测试邮箱发送流程。
        </p>
      </div>
      <AppScreen focus="overview" />
    </AbsoluteFill>
  );
};

const Scene = ({scene}: {scene: SceneProps}) => (
  <AbsoluteFill>
    <Background />
    <SceneText scene={scene} />
    <AppScreen focus={scene.focus} progress={scene.progress ?? 0} />
    {scene.focus === 'test' ? <TestWorkflow /> : null}
  </AbsoluteFill>
);

const Outro = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Background />
      <div style={{position: 'absolute', inset: 0, display: 'grid', placeItems: 'center'}}>
        <Panel
          style={{
            width: 1250,
            padding: 54,
            opacity: fade(frame, 0, 18),
            transform: `translateY(${rise(frame, 0)}px)`,
          }}
          active
        >
          <div style={{color: colors.cyan, fontSize: 22, fontWeight: 900, letterSpacing: 4}}>
            FINAL CHECK
          </div>
          <h2 style={{fontSize: 68, margin: '22px 0'}}>测试通过后再进入正式发送</h2>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 18}}>
            {['授权码脱敏保存', 'Excel 列映射正确', '测试收件箱已收到', '失败记录可导出'].map((item, index) => (
              <Panel key={item} style={{padding: 22, minHeight: 118}} active={index === 2}>
                <div style={{fontSize: 25, fontWeight: 900, lineHeight: 1.25}}>{item}</div>
              </Panel>
            ))}
          </div>
          <p style={{fontSize: 28, color: colors.secondary, margin: '34px 0 0'}}>
            视频源码在 remotion/yunyoubao-tutorial，成片输出到 out/yunyoubao-tutorial.mp4。
          </p>
        </Panel>
      </div>
    </AbsoluteFill>
  );
};

export const YunYouBaoTutorial = () => {
  const {fps} = useVideoConfig();
  const intro = 4 * fps;
  const sceneLength = 5 * fps;
  const outroStart = intro + scenes.length * sceneLength;

  return (
    <AbsoluteFill style={{backgroundColor: colors.base}}>
      <Sequence from={0} durationInFrames={intro} premountFor={fps}>
        <Intro />
      </Sequence>
      {scenes.map((scene, index) => (
        <Sequence
          key={scene.eyebrow}
          from={intro + index * sceneLength}
          durationInFrames={sceneLength}
          premountFor={fps}
        >
          <Scene scene={scene} />
        </Sequence>
      ))}
      <Sequence from={outroStart} durationInFrames={4 * fps} premountFor={fps}>
        <Outro />
      </Sequence>
    </AbsoluteFill>
  );
};
