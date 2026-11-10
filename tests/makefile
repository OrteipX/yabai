.PHONY: clean build run all diagnostics asan

SANITIZE_FLAGS =

all: clean build run

asan: SANITIZE_FLAGS = -fsanitize=address,undefined,float-cast-overflow -fno-omit-frame-pointer
asan: all

clean:
	rm -rf ./bin

build:
	mkdir -p ./bin
	clang ./src/tests.m -o ./bin/tests $(SANITIZE_FLAGS) -DTESTS -DPROFILE=1 -F/System/Library/PrivateFrameworks -framework Carbon -framework Cocoa -framework CoreServices -framework CoreVideo -framework SkyLight

	clang ./src/space_transition.m -o ./bin/space_transition $(SANITIZE_FLAGS) -mmacosx-version-min=11.0 -framework Cocoa -framework Carbon

run:
	./bin/tests
	./bin/space_transition

diagnostics:
	mkdir -p ./bin
	clang ./src/diagnostics.m -o ./bin/diagnostics -DTESTS -mmacosx-version-min=11.0 -F/System/Library/PrivateFrameworks -framework Carbon -framework Cocoa -framework CoreServices -framework CoreVideo -framework SkyLight
	./bin/diagnostics
