using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        bool silent = Array.IndexOf(args, "--silent") >= 0;
        try
        {
            if (Array.IndexOf(args, "--uninstall") >= 0)
            {
                if (silent || MessageBox.Show("卸载 B 站浏览与缓存？已下载的视频仍可在原目录播放。",
                    Install.Product, MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
                    Install.Uninstall();
            }
            else if (silent)
            {
                Install.Run(Array.IndexOf(args, "--no-desktop") < 0, delegate { });
            }
            else
            {
                Application.Run(new SetupWindow());
            }
            return 0;
        }
        catch (Exception error)
        {
            Install.Log(error.ToString());
            if (!silent)
                MessageBox.Show("操作未完成。请关闭正在运行的应用后重试。\n\n" + error.Message,
                    Install.Product, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

internal static class Install
{
    internal const string Product = "B 站浏览与缓存";
    internal const string Version = "0.1.2";
    private const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\BilibiliCache";
    private const string OwnershipMarker = ".bilibili-cache-install";
    private static readonly string Local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
    private static readonly string Data = Path.Combine(Local, "bilibili-network");
    private static readonly string Root = Path.Combine(Local, "Programs", "BilibiliCache");
    private static readonly string VersionDir = Path.Combine(Root, "app-" + Version);
    private static readonly string Maintenance = Path.Combine(Data, "Uninstall-Bilibili-Cache.exe");
    internal static readonly string LogPath = Path.Combine(Data, "setup.log");
    internal static readonly string Launcher = Path.Combine(VersionDir, "Bilibili-Download.exe");

    internal static void Run(bool desktop, Action<string> report)
    {
        Directory.CreateDirectory(Root);
        string stage = Path.Combine(Root, "setup-" + Guid.NewGuid().ToString("N"));
        if (!Directory.Exists(VersionDir))
        {
            report("正在解压应用文件…");
            Directory.CreateDirectory(stage);
            try
            {
                Unpack(stage);
                report("正在安装运行组件，首次安装可能需要几分钟…");
                InstallDependencies(stage, report);
                File.WriteAllText(Path.Combine(stage, OwnershipMarker), Version);
                Directory.Move(stage, VersionDir);
            }
            finally
            {
                if (Directory.Exists(stage))
                    RemoveOwnedChild(stage, "setup-");
            }
        }
        else if (!File.Exists(Path.Combine(VersionDir, OwnershipMarker)) || !File.Exists(Launcher)
                 || !File.Exists(Path.Combine(VersionDir, "runtime", "Lib", "site-packages", ".bili-cache-ready")))
        {
            throw new IOException("目标位置已有其他文件：" + VersionDir);
        }

        report("正在添加快捷方式和卸载入口…");
        Directory.CreateDirectory(Data);
        File.Copy(Application.ExecutablePath, Maintenance, true);
        AddShortcut(Environment.SpecialFolder.Programs);
        if (desktop)
            AddShortcut(Environment.SpecialFolder.DesktopDirectory);
        using (RegistryKey registry = Registry.CurrentUser.CreateSubKey(RegistryPath))
        {
            registry.SetValue("DisplayName", Product);
            registry.SetValue("DisplayVersion", Version);
            registry.SetValue("Publisher", "bilibili-network");
            registry.SetValue("InstallLocation", VersionDir);
            registry.SetValue("DisplayIcon", Launcher);
            registry.SetValue("UninstallString", "\"" + Maintenance + "\" --uninstall");
            registry.SetValue("NoModify", 1);
            registry.SetValue("NoRepair", 1);
        }
    }

    private static void Unpack(string stage)
    {
        const string archiveRoot = "Bilibili-Download/";
        using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("BilibiliCache.zip"))
        using (ZipArchive zip = new ZipArchive(payload, ZipArchiveMode.Read))
        {
            foreach (ZipArchiveEntry entry in zip.Entries)
            {
                if (!entry.FullName.StartsWith(archiveRoot, StringComparison.Ordinal))
                    throw new InvalidDataException("安装包目录结构无效。");
                string relative = entry.FullName.Substring(archiveRoot.Length);
                if (relative.Length == 0)
                    continue;
                string target = Path.GetFullPath(Path.Combine(stage, relative));
                if (!target.StartsWith(stage + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("安装包包含无效的文件路径。");
                if (entry.Name.Length == 0)
                    Directory.CreateDirectory(target);
                else
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    entry.ExtractToFile(target);
                }
            }
        }
    }

    private static void InstallDependencies(string stage, Action<string> report)
    {
        string script = Path.Combine(stage, "app", "setup_runtime.py");
        using (Process process = new Process())
        {
            process.StartInfo = new ProcessStartInfo(Path.Combine(stage, "runtime", "python.exe"),
                "-B \"" + script + "\" --install-only")
            {
                UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true,
                RedirectStandardError = true, RedirectStandardInput = true, WorkingDirectory = stage
            };
            DataReceivedEventHandler output = delegate(object sender, DataReceivedEventArgs line)
            {
                if (line.Data == null)
                    return;
                Log(line.Data);
                if (line.Data.StartsWith("Installing collected packages", StringComparison.Ordinal))
                    report("下载已完成，正在安装运行组件…");
            };
            process.OutputDataReceived += output;
            process.ErrorDataReceived += output;
            process.Start();
            process.StandardInput.Close();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            process.WaitForExit();
            if (process.ExitCode != 0 || !File.Exists(Path.Combine(stage, "runtime", "Lib", "site-packages", ".bili-cache-ready")))
                throw new IOException("运行组件安装失败。确认网络可用后可重试，详细信息已写入 setup.log。");
        }
    }

    private static string ShortcutPath(Environment.SpecialFolder folder)
    {
        return Path.Combine(Environment.GetFolderPath(folder), Product + ".lnk");
    }

    private static void AddShortcut(Environment.SpecialFolder folder)
    {
        dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        string path = ShortcutPath(folder);
        dynamic shortcut = shell.CreateShortcut(path);
        if (File.Exists(path))
        {
            string target = shortcut.TargetPath;
            string directory = Path.GetDirectoryName(target);
            if (String.IsNullOrEmpty(directory)
                || !String.Equals(Path.GetDirectoryName(directory), Root, StringComparison.OrdinalIgnoreCase)
                || !Path.GetFileName(directory).StartsWith("app-", StringComparison.OrdinalIgnoreCase)
                || !String.Equals(Path.GetFileName(target), Path.GetFileName(Launcher), StringComparison.OrdinalIgnoreCase)
                || !File.Exists(Path.Combine(directory, OwnershipMarker)))
                return;
        }
        shortcut.TargetPath = Launcher;
        shortcut.IconLocation = Launcher + ",0";
        shortcut.WorkingDirectory = VersionDir;
        shortcut.Description = "浏览 B 站并缓存视频";
        shortcut.Save();
    }

    internal static void Uninstall()
    {
        if (Directory.Exists(VersionDir))
        {
            if (!File.Exists(Path.Combine(VersionDir, OwnershipMarker)))
                throw new IOException("未找到安装标记。");
            string pending = Path.Combine(Root, "remove-" + Guid.NewGuid().ToString("N"));
            Directory.Move(VersionDir, pending);
            RemoveOwnedChild(pending, "remove-");
        }
        RemoveShortcut(Environment.SpecialFolder.DesktopDirectory);
        RemoveShortcut(Environment.SpecialFolder.Programs);
        Registry.CurrentUser.DeleteSubKeyTree(RegistryPath, false);
    }

    private static void RemoveShortcut(Environment.SpecialFolder folder)
    {
        string path = ShortcutPath(folder);
        if (!File.Exists(path))
            return;
        dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        dynamic shortcut = shell.CreateShortcut(path);
        if (String.Equals((string)shortcut.TargetPath, Launcher, StringComparison.OrdinalIgnoreCase))
            File.Delete(path);
    }

    private static void RemoveOwnedChild(string path, string prefix)
    {
        string full = Path.GetFullPath(path);
        if (!String.Equals(Path.GetDirectoryName(full), Root, StringComparison.OrdinalIgnoreCase)
            || !Path.GetFileName(full).StartsWith(prefix, StringComparison.Ordinal))
            throw new IOException("操作路径无效。");
        Directory.Delete(full, true);
    }

    internal static void Log(string message)
    {
        lock (LogPath)
        {
            try
            {
                Directory.CreateDirectory(Data);
                File.AppendAllText(LogPath, DateTime.Now.ToString("s") + " " + message + Environment.NewLine);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }
}

internal sealed class SetupWindow : Form
{
    private readonly Label status;
    private readonly ProgressBar progress;
    private readonly CheckBox desktop;
    private readonly Button install;
    private readonly Button done;
    private bool running;
    private bool completed;

    internal SetupWindow()
    {
        Text = Install.Product + " 安装程序";
        Icon = System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        ClientSize = new Size(560, 326);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        Font = new Font("Microsoft YaHei UI", 10);
        BackColor = Color.White;

        Panel header = new Panel { Dock = DockStyle.Top, Height = 82, BackColor = Color.FromArgb(25, 52, 56) };
        header.Controls.Add(new Label { Text = Install.Product, ForeColor = Color.White,
            Font = new Font(Font.FontFamily, 19, FontStyle.Bold), AutoSize = true, Location = new Point(24, 23) });
        Controls.Add(header);
        Controls.Add(new Label { Text = "安装到当前 Windows 用户，完成后即可从开始菜单打开。",
            Location = new Point(25, 107), Size = new Size(510, 28) });
        desktop = new CheckBox { Text = "创建桌面快捷方式", Checked = true, AutoSize = true, Location = new Point(26, 147) };
        Controls.Add(desktop);
        status = new Label { Text = "首次安装需要联网获取运行组件。", Location = new Point(25, 190), Size = new Size(510, 47) };
        Controls.Add(status);
        progress = new ProgressBar { Location = new Point(26, 238), Size = new Size(507, 14), Maximum = 100 };
        Controls.Add(progress);
        install = new Button { Text = "安装", Location = new Point(330, 274), Size = new Size(96, 32) };
        done = new Button { Text = "取消", Location = new Point(438, 274), Size = new Size(96, 32) };
        install.Click += StartInstall;
        done.Click += delegate { Close(); };
        Controls.Add(install);
        Controls.Add(done);
        AcceptButton = install;
        FormClosing += delegate(object sender, FormClosingEventArgs e) { e.Cancel = running; };
    }

    private void StartInstall(object sender, EventArgs args)
    {
        if (completed)
        {
            Process.Start(new ProcessStartInfo(Install.Launcher) { UseShellExecute = true });
            Close();
            return;
        }
        bool shortcut = desktop.Checked;
        running = true;
        desktop.Enabled = install.Enabled = done.Enabled = false;
        progress.Style = ProgressBarStyle.Marquee;
        progress.MarqueeAnimationSpeed = 28;
        Thread worker = new Thread(delegate()
        {
            Exception failed = null;
            try
            {
                Install.Run(shortcut, delegate(string text) { BeginInvoke(new Action(delegate { status.Text = text; })); });
            }
            catch (Exception error)
            {
                failed = error;
                Install.Log(error.ToString());
            }
            BeginInvoke(new Action(delegate { Finish(failed); }));
        });
        worker.IsBackground = true;
        worker.SetApartmentState(ApartmentState.STA);
        worker.Start();
    }

    private void Finish(Exception error)
    {
        running = false;
        install.Enabled = done.Enabled = true;
        progress.Style = ProgressBarStyle.Continuous;
        if (error == null)
        {
            completed = true;
            progress.Value = 100;
            status.Text = "安装完成。";
            install.Text = "打开应用";
            done.Text = "完成";
        }
        else
        {
            progress.Value = 0;
            status.Text = error.Message;
            desktop.Enabled = true;
            install.Text = "重试";
        }
    }
}
