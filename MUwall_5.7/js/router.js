function showView(viewId) {
    // 隐藏所有视图
    const views = ['home-view', 'categories-view', 'search-view', 'profile-view'];
    views.forEach(v => {
        const el = document.getElementById(v);
        if (el) el.style.display = 'none';
    });

    // 显示目标视图
    const target = document.getElementById(viewId);
    if (target) {
        target.style.display = 'block';
        window.scrollTo(0, 0);
    }
}