# Go 学习备忘

## 错误处理

Go 没有 try/catch，用返回值传错误。函数的最后一个返回值通常是 error 类型：

```go
result, err := doSomething()
if err != nil {
    return nil, fmt.Errorf("doSomething failed: %w", err)
}
```

`%w` 会包裹（wrap）底层错误，调用者可以用 `errors.Is` / `errors.As` 判断具体错误类型。这种显式风格啰嗦但清晰 —— 你能看到每一处可能出错的地方。

对比 Java 的受检异常和 Python 的抛出异常，Go 的哲学是：错误是普通值，值得像其他数据一样对待。

## 并发原语

Go 的招牌是 goroutine 和 channel。

`go f()` 启动一个协程，几乎零成本。channel 用来在协程间传数据：

```go
ch := make(chan int, 10)   // 带缓冲的 channel
go func() {
    ch <- 42
}()
value := <-ch
```

有句名言："Don't communicate by sharing memory; share memory by communicating." —— 不要通过共享内存来通信，而应通过通信来共享内存。

## 项目组织

`go.mod` 是模块声明文件，类似 Java 的 pom.xml 或 Node 的 package.json：

```
module github.com/yourname/project

go 1.22

require (
    github.com/some/package v1.2.3
)
```

`go mod tidy` 自动整理依赖 —— 删掉没用的，补齐缺失的。

## Slice 的坑

Slice 底层是数组的视图（有长度和容量）。这个设计埋了几个陷阱：

- append 可能扩容，也可能不扩容。不扩容时修改会影响原 slice
- 传给函数时是"引用语义"，但 append 又可能让引用失效
- 从大 slice 截取小 slice，底层数组不会释放（可能造成"内存泄漏"）

被这三条坑过之后，我养成习惯：需要"独立"数据时就 `make + copy`，别偷懒直接切片。
