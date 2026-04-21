public class OuterClass implements IProcessor {
    
    private String name;
    
    public static class StaticNested {
        public void nestedMethod() {
            System.out.println("Static nested method");
        }
    }
    
    public class InnerClass {
        private int value;
        
        public InnerClass(int value) {
            this.value = value;
        }
        
        public int getValue() {
            return value;
        }
    }
    
    @Override
    public void process(String data) {
        System.out.println("Processing: " + data);
    }
    
    @Override
    public String getResult() {
        return "Result: " + name;
    }
    
    @Override
    public boolean isValid() {
        return name != null && !name.isEmpty();
    }
}
