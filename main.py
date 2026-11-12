if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        from slidesnap.smoke import main
        raise SystemExit(main(sys.argv[2:]))
    else:
        from slidesnap.app import main
        raise SystemExit(main())
